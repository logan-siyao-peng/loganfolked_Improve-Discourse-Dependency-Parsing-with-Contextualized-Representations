import sys
sys.path.append('./pytorch_models')
sys.path.append('./utils')
import argparse
from tqdm import tqdm
from UAS_parsing import assembled_sentence_execution, wrapper_model
import pickle
import torch
import numpy as np
from transformers import AutoTokenizer
from relation_labeling import build_relation_list, assembled_transform_heads, transform_heads_simple
from models import BertArcNet, BertRelationNet, RelationLSTMTagger
# bert = AutoModel.from_pretrained("bert-base-chinese")

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

def main():
    #parse the arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer_name", default="bert-base-uncased", type=str)
    parser.add_argument("--model_name", default="bert-base-uncased", type=str)
    parser.add_argument("--dataset", default="scidtb", type=str)
    parser.add_argument("--path_test_data", default='preprocessed_data/sci_test.data', type=str)
    parser.add_argument("--path_in_sentence_model", default='trained_models/SciDTB/sciDTB_in_sentence.pt', type=str)
    parser.add_argument("--path_between_sentence_model", default='trained_models/SciDTB/sciDTB_between_sentence.pt', type=str)
    #stacked = stacked bilstm proposed in the paper, naive = direct bert classification
    parser.add_argument("--relation_labeling_option", default='stacked', type=str)
    #path to the finetuned BertRelationNet for first-level represetation
    parser.add_argument("--path_relation_bert", default='trained_models/SciDTB/sciDTB_relation_bert.pt', type=str)
    #path to the finetuned BertRelationNet for second-level represetation
    parser.add_argument("--path_between_bert", default='trained_models/SciDTB/sciDTB_between_bert.pt', type=str)
    #path to the trained RelationLSTMTagger for first-level represetation
    parser.add_argument("--path_lstm_tagger", default='trained_models/SciDTB/sciDTB_lstm_tagger.pt', type=str)
    #path to the trained RelationLSTMTagger for second-level represetation
    parser.add_argument("--path_between_tagger", default='trained_models/SciDTB/sciDTB_between_tagger.pt', type=str)
    #path to a BertRelationNet for direct relation classification
    parser.add_argument("--path_simple_relation_net", default='trained_models/SciDTB/sciDTB_relation_bert.pt', type=str)
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_name)
    with open(args.path_test_data,'rb') as fb:
        test_data = pickle.load(fb)
    in_sentence_model = torch.load(args.path_in_sentence_model, map_location=torch.device(device)).eval().to(device)
    between_sentence_model = torch.load(args.path_between_sentence_model, map_location=torch.device(device)).eval().to(device)

# with open('cdtb_test.data','rb') as fb:
#   test_data = pickle.load(fb)
# relation_list = build_relation_list('test_data')
# print(relation_list)
# in_sentence_model = torch.load('cdtb_dep/trained_models/cdtb_in_sentence.pt').eval()
# between_sentence_model = torch.load('cdtb_dep/trained_models/cdtb_between_sentence.pt').eval()
    relation_list = build_relation_list(args.dataset)

    right = 0
    wrong = 0
    predicted_heads = []
    #do the tree parsing
    for i,edus in tqdm(enumerate(test_data)):
        with torch.no_grad():
            heads = assembled_sentence_execution(edus,wrapper_model(in_sentence_model),\
                                         wrapper_model(between_sentence_model),
                                         tokenizer)
        predicted_heads.append(heads)
        this_right = 0
        this_wrong = 0
        for edu in edus:
            if heads[edu.id] == edu.head:
                right += 1
                this_right += 1
            else:
                wrong += 1
                this_wrong += 1

    #if choose to not do relation labeling
    if args.relation_labeling_option == 'none':
        print("The number of UAS right is "+ str(right))
        print("The number of UAS wrong is "+ str(wrong))
        print("UAS is "+str(right/(right+wrong)))
        return

    in_sentence_model = in_sentence_model.cpu()
    between_sentence_model = between_sentence_model.cpu()

    #load the models for relation tagging
    if args.relation_labeling_option == 'stacked':
        relation_bert = torch.load(args.path_relation_bert, map_location=torch.device(device)).bert.eval().to(device)
        # relation_bert.gradient_checkpointing_enable() # Logan
        between_bert = torch.load(args.path_between_bert, map_location=torch.device(device)).bert.eval().to(device)
        # between_bert.gradient_checkpointing_enable() # Logan
        lstm_tagger = torch.load(args.path_lstm_tagger, map_location=torch.device(device)).eval().to(device).double()
        lstm_tagger.hidden = (lstm_tagger.hidden[0].to(device),lstm_tagger.hidden[1].to(device))
        between_tagger = torch.load(args.path_between_tagger, map_location=torch.device(device)).eval().to(device).double()
        between_tagger.hidden = (between_tagger.hidden[0].to(device), between_tagger.hidden[1].to(device))
    else:
        simple_relation_net = torch.load(args.path_simple_relation_net, map_location=torch.device(device)).eval().to(device)

    #do the relation tagging
    LASright = 0
    LASwrong = 0
    for i,edus in tqdm(enumerate(test_data)):
        heads = predicted_heads[i]
        with torch.no_grad():
            if args.relation_labeling_option == 'stacked':
                relations = assembled_transform_heads(heads, edus, relation_bert = relation_bert,\
                                lstm_tagger = lstm_tagger, between_relation_bert = between_bert,
                                between_tagger = between_tagger, relation_list = relation_list,
                                tokenizer = tokenizer)
            else:
                relations =  transform_heads_simple(heads, edus, simple_relation_net, relation_list, tokenizer)
        for edu in edus:
            if heads[edu.id] == edu.head and (relations[edu.id] == edu.relation or edu.relation == 'ROOT'):
                LASright += 1
            else:
                LASwrong+= 1

    print("The number of right is "+ str(right))
    print("The number of wrong is "+ str(wrong))
    print("UAS is "+str(right/(right+wrong)))
    print(f'LAS is {LASright/(LASright + LASwrong)}')

if __name__ == "__main__":
    main()

