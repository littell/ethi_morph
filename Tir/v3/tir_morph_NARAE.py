#!/usr/bin/env python
# -*- coding: utf-8 -*-
# version 3:
# Improved morphological grammar (additional verbal prefixes, affixes cleaned up)
# Utilizes (1) multiple dictionaries: _2 came from additional dict source, _3 hand-entered,
#                                    plus gazetteer-extracted one. 
#          (2) pre-parsed file lookup: hornmorpho includes 5700 pre-parsed verb entries.

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


def process_preparsed_dict(dict_filename_list):
    preparsed = defaultdict(list)

    for dict_filename in dict_filename_list:
        with open(dict_filename, "r", encoding="utf-8") as fin:
            for line in fin.readlines():
                if line.startswith("#"): continue  # ignore comment lines
                parts = line.split("\t")
                # TIR, IPA, Gloss, Natural, Lemma, Breakdown, Comments
                if len(parts) < 7:
                    print("WARNING: Insufficient parts for line %s" % line)
                    continue
                tir, ipa, gloss, natural, lemma, breakdown, comment = tuple(parts)
                ipa = g2p(tir)
                if gloss == "": gloss = ipa
                if lemma == "": lemma = ipa
                if breakdown == "": breakdown = ipa
                preparsed[ipa] = [{'breakdown':breakdown, 'lemma':lemma, 'gloss':gloss, 'natural':natural}]
    
    return preparsed


def get_dictionary(dict_filename_list):
    l1_to_l2 = defaultdict(list)

    for dict_filename in dict_filename_list:
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

"""1 2 3   PL SG   MASC FEM
PERF IMPERF PRES
ITER GERNDV IMP REL PASS RECIP TRANS PREP
Q NEG"""

V_INITIAL = ( Before('ə') | Before('ɨ') | Before('a') | Before('i') | 
            Before('o') | Before('u') | Before('e') )

SCHWA_INITIAL = Before('ə')

V_FINAL = ( After('ə') | After('ɨ') | After('a') | After('i') | 
            After('o') | After('u') | After('e') )

TRUNC_PLU_OT = ( Truncate("aj", Tex) | Truncate("a", Tex))
TRUNC_PLU_WITI = Truncate("t", Tex)

REL = ( Aff('zɨ') + Gloss('REL') + Nat("which (.*)")
        | NULL)

CONJ = ( Aff('ki') + Gloss('CONJ') + Nat("and (.*)")
       | Aff('mɨ') + Gloss('CONJ') + Nat("and (.*)")
        | NULL)

NEG = ( Tex('ʔaj(.+)ɨn') + Gloss('NEG')  + Nat("not (.*)") 
        | Tex('ʔaj(.+)n') + Gloss('NEG')  + Nat("not (.*)") 
        | Tex('ʔajɨ(.+)n') + Gloss('NEG')  + Nat("not (.*)") 
        | Tex('ʔajɨ(.+)ɨn') + Gloss('NEG')  + Nat("not (.*)") 
        | Tex('ʔajɨtɨ(.+)ɨn') + Gloss('NEG')  + Nat("don't (.*)")  # negative imperative
        | NULL )
    
TENSE = ( Aff('kɨ') + Gloss('FUT') + Nat ("will (.*)")
    | Aff('tə') + Gloss('PERF') + Nat ("did (.*)")
    | Aff('jɨ') + Gloss('PERF') + Nat ("did (.*)")
    | NULL)


NUMBER = (
     ~V_FINAL + Aff('at')   + Gloss('PL') + Nat("multiple (.*)")   # after C (ዓራት > ዓራታት) (ʕarat - at) 'beds'
    | V_FINAL + Aff('tat')  + Gloss('PL') + Nat("multiple (.*)")   # after V (እምባ > እምባታት) (ʔɨmɨba - tat) 'mountains'
    | TRUNC_PLU_OT + Aff('ot')   + Gloss('PL') + Nat("multiple (.*)")   # following deletion of -a or -aj
                                                                      # (ሓረስታይ > ሓረስቶት) (ħarəsɨtaj > ħarəsɨtot )
    | (V_FINAL | TRUNC_PLU_WITI) + Aff('wɨti') + Gloss('PL') + Nat("multiple (.*)")
                                             # after V (ገዛ > ገዛውቲ) (ɡəza-wɨti) 'houses'
                                             # or t which gets deleted (ዓራት > ዓራውቲ) (ʕarat > ʕarawɨti) 'beds'
    | ~V_FINAL + Aff('ɨti')   + Gloss('PL') + Nat("multiple (.*)")   # after C
    | NULL
)


# Below from https://en.wikipedia.org/wiki/Tigrinya_grammar
# Need to take care of POL (polite) forms. 
POSS = (
      ~V_FINAL + Aff('əj')      + Gloss('1SG.POSS')        + Nat("my (.*)")    # after C
    |  V_FINAL + Aff('j')       + Gloss('1SG.POSS')        + Nat("my (.*)")    # after V
    | Aff('ka')        + Gloss('2SG.MASC.POSS')   + Nat("your (.*)")
    | Aff('ki')        + Gloss('2SG.FEM.POSS')    + Nat("your (.*)")
    | ~V_FINAL + Aff('u')        + Gloss('3SG.MASC.POSS')   + Nat("his (.*)")   # after C
    |  V_FINAL + Aff('ʔu')       + Gloss('3SG.MASC.POSS')   + Nat("his (.*)")   # glottal after V
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
# CC pattern needs changing
PRONCLITIC_OBLIQ = (
      Aff('ləj')      + Gloss('1SG.OBL')        + Nat("(.*) to me")   # well represented
    | Aff('lɨka')        + Gloss('2SG.MASC.OBL')   + Nat("(.*) to you") # lots of fusion, not very common
    | Aff('lɨki')        + Gloss('2SG.FEM.OBL')    + Nat("(.*) to you") # only 3! 
    | Aff('lu')        + Gloss('3SG.MASC.OBL')   + Nat("(.*) to him") # lots of fusion, some mulu/kumulu
    | Aff('la')        + Gloss('3SG.FEM.OBL')    + Nat("(.*) to her") # well represented, relatively clean break. 
    | Aff('lɨna')        + Gloss('1PL.OBL')        + Nat("(.*) to us") # well represented
    | Aff('lɨkum')    + Gloss('2PL.MASC.OBL')     + Nat("(.*) to you") # 20? looks ok
    | Aff('lɨn')    + Gloss('2PL.FEM.OBL')      + Nat("(.*) to you") # almost always involves ə -> ɨ on stem, l could be part of stem
    | Aff('lom')    + Gloss('3PL.MASC.OBL')     + Nat("(.*) to them") # almost always lə -> lom on stem. 
    | Aff('lən')      + Gloss('3PL.FEM.OBL')      + Nat("(.*) to them") + Cost("XXXX") # relatively clean break when occurs.
                                                      # but lots of false positives with lə+n
    | NULL      
    )

# Additional forms need entering. 
PRONCLITIC_OBJ = (
      Aff('ni')     + Gloss('1SG.OBJ')        + Nat("(.*) me") 
    | Aff('ka')     + Gloss('2SG.MASC.OBJ')   + Nat("(.*) you")
    | Aff('ki')     + Gloss('2SG.FEM.OBJ')    + Nat("(.*) you")  # very few of them
    | Aff('jo')     + Gloss('3SG.MASC.OBJ')   + Nat("(.*) him")  # najo also frequent
    | Aff('ʔo')     + Gloss('3SG.MASC.OBJ')   + Nat("(.*) him") 
    | Aff('wo')     + Gloss('3SG.MASC.OBJ')   + Nat("(.*) him")  # lots of kɨwo
    | Aff('ja')     + Gloss('3SG.FEM.OBJ')    + Nat("(.*) her")
    | Aff('wa')     + Gloss('3SG.FEM.OBJ')    + Nat("(.*) her")
    | Aff('ʔa')     + Gloss('3SG.FEM.OBJ')    + Nat("(.*) her") + Cost("XXXX") # Lots of fusion
    | Aff('na')     + Gloss('1PL.OBJ')        + Nat("(.*) us")   # lɨna also frequent
    | Aff('kum')    + Gloss('2PL.MASC.OBJ')     + Nat("(.*) you")   # lɨkum also common
    | Aff('kɨn')    + Gloss('2PL.FEM.OBJ')      + Nat("(.*) you")   # **0** tokens! Huh. 
    | Aff('jom')    + Gloss('3PL.MASC.OBJ')     + Nat("(.*) them")   # Oh dear. jə/wə -> jom. MESSY. 
    | Aff('ʔom')    + Gloss('3PL.MASC.OBJ')     + Nat("(.*) them")   # Likewise. ʔə -> ʔom. No clean boundary. 
    | Aff('jən')      + Gloss('3PL.FEM.OBJ')      + Nat("(.*) them") + Cost("XXXX")
                                    # infrequent. Most string matches are false positives: j+ən
    | NULL      
    )


# Case markers prefix to nouns. 
CASE = (
    Aff('nɨ')            + Gloss('ACC') + Nat("(OBJ-)") 
    | NULL
)

dict_path = "/usr2/data/shared/LoReHLT17/internal/Morph/Tir/v3/"  # on lor
#dict_path = "D:\\Projects\\LORELEI Surprise Language\\morphology\\v3\\"  # SWITCH 

# These files list fully parsed entries. 
dict_preparsed = [dict_path+"IL5_PREPARSED.tsv", dict_path+"IL5_PREPARSED_hornmorpho.tsv"]
preparsed = process_preparsed_dict(dict_preparsed)

# Below are dictionary files. First two fields are absolutely necessary: eng_definition, tir_word. 
dict_list = [dict_path+"IL5_dictionary_1.txt", dict_path+"IL5_dictionary_2.txt",
             dict_path+"IL5_dictionary_3_SUPPL.txt", dict_path+"tir_gaz.txt"]
ROOT      = Lookup(dict_list, Text/Breakdown/Lemma, Gloss/Nat)
#ROOT = Guess(Lem)   # SWITCH FOR GRAMMAR BUILDING!! 

MATRIX = (CASE|TENSE) >> ROOT << NUMBER << (POSS | PRONCLITIC_OBLIQ | PRONCLITIC_OBJ) << NEG
PARSER = (REL|CONJ) >> MATRIX
# integrating two yields error for ዝክርን zɨkɨrɨn. Cannot do PARSER = REL >> FUT >> ROOT 


##############################
#
# CONVENIENCE FUNCTIONS
#
##############################

@lru_cache(maxsize=1000)
def parse(word, representation_name="lemma"):
    ipa = g2p(word)
    parses = PARSER.parse(ipa)

    if ipa in preparsed: parses = preparsed[ipa]  # pre-parsed takes priority
    # Maybe it's better to merge this with the parsed output above, rather than replacing

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
    
    testprint_ipa = lambda x: print(json.dumps(PARSER.parse(x), ensure_ascii=False), "\n")
    
    # testprint_ipa(g2p('ንኣልማዝ'))   # from Ge'ez input, same as below
    testprint_ipa('nɨʔalɨmaz')   # nɨ-ʔalɨmaz  Almaz-ACC (Accusative marking on noun, can be 'for')

    testprint_ipa('rɨʔɨjəja')   # ርእየያ rɨʔɨ-jəja    (I-)saw-her (object pronoun suffix on verb)

    testprint_ipa('ʔajɨsɨbəruləjɨn') # neg 'ኣይስበሩለይን'  'ʔaj-' & '-ɨn' form NEG: 'they are not broken for me'
    testprint_ipa('jɨsɨbəruləj') # pron'ይስበሩለይ'  "-ləj" is 1st personal pronoun clitic: 'they are broken for me'   

    testprint_ipa('ʔɨmɨbatat') # plural 'tat' እምባታት "mountains"
    testprint_ipa('ʕaratat') # plural 'at' ዓራታት "beds"
    testprint_ipa('ɡəzawɨti') # plural 'wɨti' ገዛውቲ "houses"
    testprint_ipa('ħarəsɨtot') # plural 'ot' after deletion of 'a' or 'aj'. (ሓረስታይ > ሓረስቶት) (ħarəsɨtaj > ħarəsɨtot )
    testprint_ipa('ʕarawɨti') # (ዓራት > ዓራውቲ) (ʕarat > ʕarawɨti) 'beds'
    

