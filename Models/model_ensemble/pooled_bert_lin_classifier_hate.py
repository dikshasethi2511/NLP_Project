# -*- coding: utf-8 -*-
"""BERT_CLASSIFIER.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/13s_yhJi2rvqc2WZ9ffpZjc20gXY3zU3d
"""

# using bert sequence classifier from hugging face 
# https://huggingface.co/docs/transformers/v4.24.0/en/model_doc/bert#transformers.BertForSequenceClassification
# !pip install transformers

# from google.colab import drive
# drive.mount('/content/drive')

import torch
from transformers import BertTokenizer, BertForSequenceClassification 
import pandas as pd
import os
from torch import nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
import numpy as np
from sklearn.metrics import f1_score

# dataset = np.array(pd.read_csv('/content/drive/MyDrive/NLP_Project_sem5/processed_data.csv'))
# dataset = pd.read_csv('/content/drive/MyDrive/NLP_Project_sem5/processed_data.csv')

train_dataset = pd.read_csv('/raid/home/vibhu20150/temp/Datasets-Processed/H3_Multiclass_Hate_Speech_Detection_train_preprocessed.csv')
test_dataset = pd.read_csv('/raid/home/vibhu20150/temp/Datasets-Processed/H3_Multiclass_Hate_Speech_Detection_test_preprocessed.csv')
hate_aug_dataset = pd.read_csv('/raid/home/vibhu20150/temp/Datasets-Processed/HateSpeech_Augmented_NEW.csv')


print(train_dataset)
print(test_dataset)

print(train_dataset.shape)
# print(dataset[0,2])
print(train_dataset)
print(test_dataset.shape)
# print(dataset[0,2])
print(test_dataset)

from torch.utils.data import Dataset


class CustomSingleDataset(Dataset):
    def __init__(self, dataset, aug_hate, num_hate,tokenizer, class_type="hate"):
        if class_type == "all":
            self.labels = [label for label in dataset['label']]
            self.tweets = [tokenizer(tweet, max_length=250, padding='max_length', truncation=True, return_tensors="pt") for tweet in dataset['tweet']]
        elif class_type == "hate":
            self.labels = [int(label==0) for label in dataset['label']]
            self.tweets = [tokenizer(tweet, max_length=250, padding='max_length', truncation=True, return_tensors="pt") for tweet in dataset['tweet']]
            self.labels.extend([1 for i in range(num_hate)])
            self.tweets.extend([tokenizer(tweet, max_length=250, padding='max_length', truncation=True, return_tensors="pt") for tweet in aug_hate['tweet'][:num_hate]])
        elif class_type == "offensive":
            self.labels = [int(label==1) for label in dataset['label']]
            self.tweets = [tokenizer(tweet, max_length=250, padding='max_length', truncation=True, return_tensors="pt") for tweet in dataset['tweet']]
        elif class_type == "none":
            self.labels = [int(label==2) for label in dataset['label']]
            self.tweets = [tokenizer(tweet, max_length=250, padding='max_length', truncation=True, return_tensors="pt") for tweet in dataset['tweet']]
            

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        tweet = self.tweets[idx]
        label = self.labels[idx]

        return tweet, label

    def getLabels(self):
        return self.labels

# sequence classification/regression head on top a linear layer on top of the pooled output of BERT
from transformers import BertModel


class BertSeqPoolLinClassifier(nn.Module):
    def __init__(self):
        super(BertSeqPoolLinClassifier, self).__init__()
        self.bert = BertModel.from_pretrained("bert-base-uncased")
        self.linear_layer_1 = nn.LazyLinear(100)
        self.linear_layer = nn.LazyLinear(1)

        self.pooling_layer = nn.AvgPool1d(384, stride=192)
        self.relu = nn.ReLU()
        self.tan_h = nn.Tanh()
        # self.soft_max = nn.Softmax(dim=3) 

    def forward(self, input_ids, bert_mask):
        seq_last_hidden_states, pooled_output = self.bert(input_ids=input_ids, attention_mask=bert_mask, return_dict=False)
        # print("SEQ SHAPE: ", seq_last_hidden_states.shape) 
        # print("Pool Shape: ", pooled_output.shape)
        pooled_hidden_states = self.pooling_layer(seq_last_hidden_states)
        pooled_hidden_states = pooled_hidden_states.reshape(pooled_output.shape[0], -1)
        linear_output_1 = self.tan_h(self.linear_layer_1(pooled_hidden_states))
        linear_output = self.relu(self.linear_layer(linear_output_1))
        # probs = self.soft_max(linear_output) # already incorporated in crossentropyLoss
        # return probs
        return linear_output

from tqdm import tqdm
from torch.utils.data import DataLoader

def train(model, train_data, test_data, learning_rate_bert, learning_rate_lin, epochs, device):
    model.train()
    # loss_function = nn.CrossEntropyLoss()
    loss_function = nn.BCEWithLogitsLoss() # incorporates sigmoid in the loss itself, somehow helps in numeric stability or something vs normal BCE loss
    optimizer = torch.optim.AdamW([
        {'params': model.bert.parameters(), 'lr': learning_rate_bert},
        {'params': model.linear_layer_1.parameters()},
        {'params': model.linear_layer.parameters()}
        ], lr=learning_rate_lin)

    if(device == "cuda"):
        model.cuda()
        loss_function.cuda()

    
    batch_size = 8
    train_dataloader = DataLoader(train_data, batch_size=batch_size, shuffle=True)
    test_dataloader = DataLoader(test_data, batch_size=batch_size)
    
    best_score = 0.0
    
    for epoch in tqdm(range(epochs)):

        correct_preds = 0
        train_preds = []
        test_preds = []

        for batch, (tweets, labels) in enumerate(train_dataloader):
            
            labels = labels.to(device)

            output = model(tweets["input_ids"].squeeze(1).to(device), tweets["attention_mask"].to(device))
            # print(f"label shape: {labels.shape}") # should be batch X 1
            # print(output)
            # print(labels)
            loss = loss_function(output.squeeze(), labels.float()) 
            # print("output shape: ", output.shape)
            
            # preds = model() 

            # update
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()


            # accuracy 
            # print("OUTPUT SHAPE: ", output.shape)
            # preds = output.argmax(dim=1)
            preds = []
            # print("preds shape: ", preds.shape)
            # print("labels shape: ", len(labels))

            for i in range(len(labels)):
                # print(i)
                if output[i].item() < 0.5:
                    preds.append(torch.tensor(0).cpu())
                else:
                    preds.append(torch.tensor(1).cpu())
                train_preds.append(preds[i].cpu())
                if preds[i] == labels[i]:
                    correct_preds += 1
            
        
        


        # testing code 

        test_correct_preds = 0

        with torch.no_grad():
            for batch, (tweets, labels) in enumerate(test_dataloader):
                labels = labels.to(device)
                # print()
                # print("="*40)
                # print()
                # print(tweets["attention_mask"].shape)
                # print()
                output = model(tweets["input_ids"].squeeze(1).to(device), tweets["attention_mask"].to(device))
                # print(f"label shape: {labels.shape}") # should be batch X 1
                # loss = loss_function(output, labels)
                # print("output shape: ", output.shape)
                
                # preds = model() 
                # accuracy 
                sigmoid = nn.Sigmoid()
                
                # preds = output.argmax(dim=1)
                preds = []
                # print("preds shape: ", preds.shape)
                # print("labels shape: ", labels.shape)

                for i in range(len(labels)):
                    if output[i].item() < 0.5:
                        preds.append(torch.tensor(0).cpu())
                    else:
                        preds.append(torch.tensor(1).cpu())
                    # print(i)
                    test_preds.append(preds[i].cpu())
                    if preds[i] == labels[i]:
                        test_correct_preds += 1
        

          
        print(f"\nEpoch: {epoch + 1}, Train Acc: {correct_preds/len(train_data)}, Train Length: {len(train_data)}, Test Acc: {test_correct_preds/len(test_data)}, Test Length: {len(test_data)}")
        print(f"F1 Score Train: {f1_score(train_data.getLabels(), train_preds, average=None)}")
        print(f"Macro F1 Score Train: {f1_score(train_data.getLabels(), train_preds, average='macro')}")
        print(f"F1 Score Test: {f1_score(test_data.getLabels(), test_preds, average=None)}")
        print(f"Macro F1 Score Test: {f1_score(test_data.getLabels(), test_preds, average='macro')}")
        curr_score = f1_score(test_data.getLabels(), test_preds, average='macro') 

        if curr_score > best_score:
            best_score = curr_score
            torch.save(model.bert, "./hate-model-bert.pth")
        # save best model


# !nvidia-smi

device = "cuda" if torch.cuda.is_available() else "cpu"
print(device)
torch.cuda.current_device()
torch.cuda.get_device_name(torch.cuda.current_device())


model = BertSeqPoolLinClassifier()
tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")

# model = torch.load("/ssd-scratch/vibhu20150/temp/pooled-bert-lin-3-best.pth")

print(len([para for para in model.parameters()]))
print(len([para for para in model.bert.parameters()]))
print(len([para for para in model.linear_layer.parameters()]))

labels_map = {0: "hate?",
              1: "offensive?",
              2: "none?",
              }



train_data = CustomSingleDataset(train_dataset[:17842], hate_aug_dataset, 2270, tokenizer, "hate") 
test_data = CustomSingleDataset(train_dataset[17842:], hate_aug_dataset, 0, tokenizer, "hate")

print("TRAIN LENGTH: ", len(train_data))

train(model, train_data, test_data, 0.00002, 0.001, 3, device)


# torch.save(model.state_dict(), "./trained-model-states.pth")
# torch.save(model, "./pooled-bert-3.pth")