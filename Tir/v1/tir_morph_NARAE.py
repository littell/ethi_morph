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

Text = Concatenated('text')
Breakdown = Hyphenated('breakdown')
Aff = Text / Breakdown
Def = Concatenated("definition")
Nat = Concatenated("natural")
Cost = Concatenated("cost")
Gloss = Hyphenated("gloss")
Lemma = Concatenated("lemma")
Lem = Text / Breakdown / Gloss / Lemma / Def / Nat

DEFAULTS.Text = Text
DEFAULTS.Lem = Lem



import lxml.etree as ET
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

V_INITIAL = ( Before('ə') | Before('ɨ') | Before('a') | Before('i') | 
            Before('o') | Before('u') | Before('e') )
SCHWA_INITIAL = Before('ə')

V_FINAL = ( After('ə') | After('ɨ') | After('a') | After('i') | 
            After('o') | After('u') | After('e') )

# The verb may be negated. This requires a prefix and sometimes a suffix. For example,
# the word ይስበሩለይ yǝsǝbbäruläy 'they are broken for me' is negated by the prefixing of ay-
# and the suffixing of -n: ኣይስበሩለይን ayyǝsǝbbäruläyǝn 'they are not broken for me'.
NEG = (
      Aff('ʔaj')            + Gloss('NEG')              + Nat("not (.*)") 
    | NULL
)



NUMBER = (
     ~V_FINAL + Aff('at')   + Gloss('PL') + Nat("multiple (.*)")   # after C (ዓራት > ዓራታት) (ʕarat - at) 'beds'
    | V_FINAL + Aff('tat')  + Gloss('PL') + Nat("multiple (.*)")   # after V (እምባ > እምባታት) (ʔɨmɨba - tat) 'mountains'
    |           Aff('ot')   + Gloss('PL') + Nat("multiple (.*)")   # following deletion of -a or -aj (ሓረስታይ > ሓረስቶት) (ħarəsɨtaj > ħarəsɨtot )
    | V_FINAL + Aff('wɨti') + Gloss('PL') + Nat("multiple (.*)")   # after V, or t which gets deleted
                                                                   # (ገዛ > ገዛውቲ) (ɡəza-wɨti) 'houses'
    | ~V_FINAL + Aff('ɨti')   + Gloss('PL') + Nat("multiple (.*)")   # after C
    | NULL
)

# Unlike Amharic, definite article takes on a form of separate words, so below not needed. 
# ʔɨti, ʔɨta, ʔɨtom, ʔɨtən. (SM SF PM PF)
"""
DEFINITENESS = (
      Aff('wa')            + Gloss('DEF.F')            + Nat("the (.*)") 
    | Aff('itu')          + Gloss('DEF.FEM')          + Nat("the (.*)") 
    | Aff('u')              + Gloss('DEF')              + Nat("the (.*)")           + Cost("X") 
    | Aff('wɨ')            + Gloss('DEF.MASC')         + Nat("the (.*)") 
    | Aff('w')              + Gloss('DEF.PL')           + Nat("the multiple (.*)")  + Cost("X")
    | NULL
)
"""

# Below from https://en.wikipedia.org/wiki/Tigrinya_grammar
# Need to take care of POL (polite) forms. 
POSS = (
      ~V_FINAL + Aff('əj')      + Gloss('1SG.POSS')        + Nat("my (.*)")    # after C
    |  V_FINAL + Aff('j')       + Gloss('1SG.POSS')        + Nat("my (.*)")    # after V
    | Aff('ka')        + Gloss('2SG.MASC.POSS')   + Nat("your (.*)")
    | Aff('ki')        + Gloss('2SG.FEM.POSS')    + Nat("your (.*)")
    | ~V_FINAL + Aff('u')        + Gloss('3SG.MASC.POSS')   + Nat("his (.*)")    # after C
    |  V_FINAL + Aff('ʔu')       + Gloss('3SG.MASC.POSS')   + Nat("his (.*)")    # glottal after V
    | ~V_FINAL + Aff('a')        + Gloss('3SG.FEM.POSS')    + Nat("her (.*)")   # after C
    |  V_FINAL + Aff('?a')       + Gloss('3SG.FEM.POSS')    + Nat("her (.*)")   # glottal after V
    | Aff('na')        + Gloss('1PL.POSS')        + Nat("our (.*)")
    | Aff('kum')    + Gloss('2PL.MASC.POSS')     + Nat("your (.*)")
    | Aff('kən')    + Gloss('2PL.FEM.POSS')      + Nat("your (.*)")
    | ~V_FINAL + Aff('om')    + Gloss('3PL.MASC.POSS')     + Nat("their (.*)")  # after C
    |  V_FINAL + Aff('?om')    + Gloss('3PL.MASC.POSS')     + Nat("their (.*)")  # glottal after V
    | Aff('ən')      + Gloss('3PL.FEM.POSS')      + Nat("their (.*)")
    | Aff('?en')    + Gloss('3PL.FEM.POSS')      + Nat("their (.*)")
    | NULL      
    )

# Gemmination of l needs to be figured out. 
PRONCLITIC_OBLIQ = (
      Aff('ləj')      + Gloss('1SG.OBL')        + Nat("(.*) to me") 
    | Aff('lka')        + Gloss('2SG.MASC.OBL')   + Nat("(.*) to you")
    | Aff('lki')        + Gloss('2SG.FEM.OBL')    + Nat("(.*) to you")
    | Aff('lu')        + Gloss('3SG.MASC.OBL')   + Nat("(.*) to him") 
    | Aff('la')        + Gloss('3SG.FEM.OBL')    + Nat("(.*) to her") 
    | Aff('lna')        + Gloss('1PL.OBL')        + Nat("(.*) to us")
    | Aff('lkum')    + Gloss('2PL.MASC.OBL')     + Nat("(.*) to you")
    | Aff('lkən')    + Gloss('2PL.FEM.OBL')      + Nat("(.*) to you")
    | Aff('lom')    + Gloss('3PL.MASC.OBL')     + Nat("(.*) to them")
    | Aff('lən')      + Gloss('3PL.FEM.OBL')      + Nat("(.*) to them")
    | NULL      
    )

# Gemmination is optional, turned on for now, needs figuring out. Plus multiple forms. 
PRONCLITIC_OBJ = (
      Aff('nni')      + Gloss('1SG.OBJ')        + Nat("(.*) me") 
    | Aff('kka')        + Gloss('2SG.MASC.OBJ')   + Nat("(.*) you")
    | Aff('kki')        + Gloss('2SG.FEM.OBJ')    + Nat("(.*) you")
    | Aff('jojo')        + Gloss('3SG.MASC.OBJ')   + Nat("(.*) him") 
    | Aff('jəja')        + Gloss('3SG.FEM.OBJ')    + Nat("(.*) her") 
    | Aff('nna')        + Gloss('1PL.OBJ')        + Nat("(.*) us")
    | Aff('kkum')    + Gloss('2PL.MASC.OBJ')     + Nat("(.*) you")
    | Aff('kkən')    + Gloss('2PL.FEM.OBJ')      + Nat("(.*) you")
    | Aff('jojom')    + Gloss('3PL.MASC.OBJ')     + Nat("(.*) them")   # 1st one could be ɨ, hard to tell
    | Aff('jəjən')      + Gloss('3PL.FEM.OBJ')      + Nat("(.*) them") # 1st one could be ɨ, hard to tell
    | NULL      
    )


# Case markers prefix to nouns. 
CASE = (
    Aff('nɨ')            + Gloss('ACC') 
#    | Aff('ɨ n')            + Gloss('ACC')    # from Amharic. Haven't seen, but may apply. 
#    | Aff('ɨ n ɨ')          + Gloss('ACC') 
    | NULL
)

"""
ROOT        = Guess(Lem)
LOOKUP_ROOT = Lookup(ROOT, ".", Def, Def / Nat)
WORD        = LOOKUP_ROOT << NUMBER << DEFINITENESS << POSS << CASE
PHONWORD    = WORD << ENCLITIC
PARSER      = PREP >> PHONWORD
"""

Cost = Concatenated("cost")
Nat = Concatenated("natural")

ROOT      = Lookup("IL5_dictionary.txt", Text/Breakdown/Lemma, Gloss/Nat)
PARSER = NEG >> CASE >> ROOT << NUMBER << (POSS | PRONCLITIC_OBLIQ | PRONCLITIC_OBJ)
# ROOT << (NUMBER | POSS)        # if one of them can happen but not both
# ROOT << (( N<<P )|( P<< N))   # if ordering can be either way 

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
##    with open("text-output.txt", "w", encoding="utf-8") as fout:
##        testprint = lambda x: print(json.dumps(parse(x, "natural"), indent=2, ensure_ascii=False), file=fout)
##        testprint('ያጠናልና')
##        testprint('ከዚያም')
##        testprint('አንተስ')
##        testprint('ጨውና')
##        testprint('ገንዘቤ')
##        testprint('ጥያቄህ')
##        testprint('ስራቸው')
##        testprint('ፓርቲዎች')
##        testprint('እንደማይቻልም')
##        testprint('አስታውቋል')
##        testprint('ኢብራሂም')
##        
        testprint_ipa = lambda x: print(json.dumps(PARSER.parse(x), ensure_ascii=False))
        
        # testprint_ipa(g2p('ንኣልማዝ'))   # from Ge'ez input, same as below
        testprint_ipa('nɨʔalɨmaz')   # nɨʔalɨmaz  nɨ-ʔalɨmaz  Almaz-ACC (Accusative marking on noun, can be 'for')
        print()
        testprint_ipa('rɨʔɨjəja')   # ርእየያ rɨʔɨ-jəja    (I-)saw-her (object pronoun suffix on verb)
        print()
        testprint_ipa('ʔajɨsɨbəruləjɨn') # 'ኣይስበሩለይን'  'ʔaj-' & '-ɨn' form NEG: 'they are not broken for me'
        print()
        testprint_ipa('jɨsɨbəruləj') # 'ይስበሩለይ'  "-ləj" is 1st personal pronoun clitic: 'they are broken for me'   
        print()
        testprint_ipa('ʔɨmɨbatat') # plural 'tat' "mountains"
        print()
        testprint_ipa('ʕaratat') # plural 'at' "beds"
        print()
        testprint_ipa('ɡəzawɨti') # plural 'wɨti' "houses"


