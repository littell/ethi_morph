#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import unicode_literals
from io import open
import epitran
import sys, json, glob, os, math
from copy import deepcopy
from morpar import *
import nltk
from nltk.probability import *
try:
    nltk.data.find('corpora/brown')
except LookupError:
    nltk.download('brown')
from nltk.corpus import brown

try:
    from functools import lru_cache
except ImportError:
    from functools32 import lru_cache

    
from collections import defaultdict

def log_error(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

    
######################################
#
# LOOKUP PARSER
#
# This section defines a custom parser
# that looks up a word in the LDC Amharic
# dictionary.
#
######################################

def get_freq_dist():
    freq = FreqDist()
    freq.update(brown.words())
    return freq

epi = epitran.Epitran("tir-Ethi")
g2p = epi.transliterate

def get_dictionary(dict_filename):
    l1_to_l2 = defaultdict(list)
    
    with open(dict_filename, "r", encoding="utf-8") as fin:
        for line in fin.readlines():
            parts = line.strip().split("\t")
            if len(parts) < 2:
                print("WARNING: Insufficient parts for line %s" % line)
                continue
            definition = parts[0]
            word = parts[1]
            ipa = g2p(word)
            l1_to_l2[ipa].append(definition)
    
    return l1_to_l2
            

class Lookup(Parser):

    def __init__(self, dictionary, channel=None, output_channel=None):
        self.dictionary = get_dictionary(dictionary)
        self.channel = channel
        self.output_channel = output_channel
        self.freqDist = get_freq_dist()
        self.engWords = self.freqDist.N()
    
    @lru_cache(maxsize=1000)
    def __call__(self, input, input_channel=None, leftward=False):
        results = set()
        
        text = input[input_channel.name]
        text = text.strip()
        
        output = HashableDict()
        remnant = HashableDict({input_channel.name:input_channel.typ()})
        
        for channel in self.channel:
            if channel == input_channel:
                continue
            output[channel.name] = channel.typ(text)    
                
        if text in self.dictionary:
            for definition in self.dictionary[text]:
                cost = 0
                for word in definition.split():
                    word = word.lower()
                    if word not in self.freqDist:
                        cost += 15
                    else:
                        log_freq = -math.log(self.freqDist[word] * 1.0 / self.engWords)
                        cost += math.floor(log_freq)
                output2 = deepcopy(output)
                for channel in self.output_channel:
                    output2[channel.name] = channel.typ(definition)
                output2[Cost.name] = Cost.typ("X" * int(cost))
                results.add((output2,remnant))
        else:
            #print("didn't find it: %s" % text)
            output2 = deepcopy(output)
            for channel in self.output_channel:
                output2[channel.name] = channel.typ(text.replace(" ",""))
            cost = "X" * (50 + len(text))
            output2[Cost.name] = Cost.typ(cost)
            results.add((output2,remnant))
            
        return results
    
###############################
#
# MORPHOLOGICAL GRAMMAR
#
###############################

Cost = Concatenated("cost")
Nat = Concatenated("natural")

PARSER      = Lookup("IL5_dictionary.txt", Tex/Mor/Lem, Glo/Cit/Nat)

##############################
#
# CONVENIENCE FUNCTIONS
#
##############################

@lru_cache(maxsize=1000)
def parse(word, representation_name="lemma"):
    ipa = g2p(word)
    parses = PARSER.parse(ipa)
    if not parses:
        print("Warning: cannot parse %s (%s)" % (word, ipa))
        parses = [{representation_name:ipa,"cost":""}]
    parses.sort(key=lambda x:len(x["cost"]) if "cost" in x else 0)
    return [x[representation_name] for x in parses]

@lru_cache(maxsize=1000)
def best_parse(word, representation_name="lemma"):
    return parse(word, representation_name)[0]

if __name__ == '__main__':
    # just for testing.  to use this file, import it as a library and call parse() 
    with open("text-output.txt", "w", encoding="utf-8") as fout:
        testprint = lambda x: print(json.dumps(parse(x, "gloss"), indent=2, ensure_ascii=False), file=fout)
        testprint('ከፋት')
        testprint('ኣፖፕላክሲ')
        testprint('አንተስ')
        testprint('ጨውና')
        testprint('ገንዘቤ')
        testprint('ጥያቄህ')
        testprint('ስራቸው')
        testprint('ፓርቲዎች')
        testprint('እንደማይቻልም')
        testprint('አስታውቋል')
        testprint('ኢብራሂም')
        
