#!/usr/bin/env python
# -*- coding: utf-8 -*- 
# version 4

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

#dict_path = "/home/data/LoReHLT17/internal/Morph/Tir/v4/" # on miami
dict_path = "/usr2/data/shared/LoReHLT17/internal/Morph/Tir/v4/"  # on lor
#dict_path = "D:\\Projects\\LORELEI Surprise Language\\morphology\\v4\\"  

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

# /ɨ/ is an epenthetic vowel; Epitran omits in word-final position.
# (In v4) Below works, but it allows padding of i in whole-root guess. Cost assigned to "ghost i"
# TRUNC_FINALV = ( Truncate("ɨ", Tex) + Cost("XXXXXXXX")   # Cost must be on this. CHECKED. 
#               | NULL )
# Best solution (so far) below. No need for cost assigning. tɨ > t by cost of 1 X!  And no iɨ in sight. 
I_FINAL = After('ɨ')
CONS = ( After('t') | After('m') | After('n') | After('j') )
TRUNC_FINAL_I = (  Truncate("ɨ", Tex) + CONS   # ordering crucial 
                | ~I_FINAL )

INSERT_I = ( ~V_FINAL + Tex("ɨ")
             | V_FINAL) 

REL = ( Aff('zɨ') + Gloss('REL') + Nat("which (.*)")
        | NULL )

CONJ_PREF = ( Aff('ki') + Gloss('CONJ') + Nat("and (.*)")
       | Aff('mɨ') + Gloss('CONJ') + Nat("and (.*)")
        | NULL )
#CONJ = (  # 'ʔaləjə' -> 'mələləj' Conjunction
# ('ʔɨtəxətəlom', 'təxətələ', 'follow-SBJ.3.SG.MASC-OBJ.3.PL.MASC-MOOD.PERF.PASS.REL', 'which did was follow')

NEG = ( Tex('ʔaj(.+)ɨnɨ') + Gloss('NEG')  + Nat("not (.*)") 
        | Tex('ʔaj(.+)nɨ') + Gloss('NEG')  + Nat("not (.*)") 
        | Tex('ʔajɨ(.+)nɨ') + Gloss('NEG')  + Nat("not (.*)") 
        | Tex('ʔajɨ(.+)ɨnɨ') + Gloss('NEG')  + Nat("not (.*)") 
        | Tex('ʔajɨtɨ(.+)ɨnɨ') + Gloss('NEG')  + Nat("don't (.*)")  # negative imperative
        | NULL )
    
TENSE = ( INSERT_I + Aff('kɨ') + Gloss('FUT') + Nat ("will (.*)")
    | INSERT_I + Aff('tə') + Gloss('PERF') + Nat ("did (.*)")
    | INSERT_I + Aff('jɨ') + Gloss('PERF') + Nat ("did (.*)")
    | NULL )


NUMBER = (
     ~V_FINAL + Aff('atɨ')   + Gloss('PL') + Nat("multiple (.*)")   + Cost("XXXXXXXXXXXXXX") # after C (ዓራት > ዓራታት) (ʕarat - at) 'beds'
    | V_FINAL + Aff('tatɨ')  + Gloss('PL') + Nat("multiple (.*)")   # after V (እምባ > እምባታት) (ʔɨmɨba - tat) 'mountains'
    | TRUNC_PLU_OT + Aff('otɨ')   + Gloss('PL') + Nat("multiple (.*)")   # following deletion of -a or -aj
                                                                      # (ሓረስታይ > ሓረስቶት) (ħarəsɨtaj > ħarəsɨtot )
    | (V_FINAL | TRUNC_PLU_WITI) + Aff('wɨti') + Gloss('PL') + Nat("multiple (.*)")
                                             # after V (ገዛ > ገዛውቲ) (ɡəza-wɨti) 'houses'
                                             # or t which gets deleted (ዓራት > ዓራውቲ) (ʕarat > ʕarawɨti) 'beds'
    | ~V_FINAL + Aff('ɨti')   + Gloss('PL') + Nat("multiple (.*)")   # after C
    | NULL )

# Below from https://en.wikipedia.org/wiki/Tigrinya_grammar
# Need to take care of POL (polite) forms. 
POSS = (
      ~V_FINAL + Aff('əjɨ')      + Gloss('1SG.POSS')        + Nat("my (.*)")    # after C
    |  V_FINAL + Aff('jɨ')       + Gloss('1SG.POSS')        + Nat("my (.*)")    # after V
    | INSERT_I + Aff('ka')        + Gloss('2SG.MASC.POSS')   + Nat("your (.*)")
    | INSERT_I + Aff('ki')        + Gloss('2SG.FEM.POSS')    + Nat("your (.*)")
    | ~V_FINAL + Aff('u')        + Gloss('3SG.MASC.POSS')   + Nat("his (.*)")   # after C
    |  V_FINAL + Aff('ʔu')       + Gloss('3SG.MASC.POSS')   + Nat("his (.*)")   # glottal after V
    | ~V_FINAL + Aff('a')        + Gloss('3SG.FEM.POSS')    + Nat("her (.*)")   # after C
    |  V_FINAL + Aff('?a')       + Gloss('3SG.FEM.POSS')    + Nat("her (.*)")   # glottal after V
    | INSERT_I + Aff('na')        + Gloss('1PL.POSS')        + Nat("our (.*)")
    | INSERT_I + Aff('kumɨ')    + Gloss('2PL.MASC.POSS')     + Nat("your (.*)")
    | INSERT_I + Aff('kənɨ')    + Gloss('2PL.FEM.POSS')      + Nat("your (.*)")
    | ~V_FINAL + Aff('omɨ')    + Gloss('3PL.MASC.POSS')     + Nat("their (.*)")  # after C
    |  V_FINAL + Aff('?omɨ')    + Gloss('3PL.MASC.POSS')     + Nat("their (.*)")  # glottal after V
    | Aff('ənɨ')      + Gloss('3PL.FEM.POSS')      + Nat("their (.*)")
    | INSERT_I + Aff('?enɨ')    + Gloss('3PL.FEM.POSS')      + Nat("their (.*)")
    | NULL  )

# CC pattern needs changing
PRONCLITIC_OBLIQ = (
      INSERT_I + Aff('ləjɨ')      + Gloss('1SG.OBL')        + Nat("(.*) to me")   # well represented
    | INSERT_I + Aff('lɨka')        + Gloss('2SG.MASC.OBL')   + Nat("(.*) to you") # lots of fusion, not very common
    | INSERT_I + Aff('lɨki')        + Gloss('2SG.FEM.OBL')    + Nat("(.*) to you") # only 3! 
    | INSERT_I + Aff('lu')        + Gloss('3SG.MASC.OBL')   + Nat("(.*) to him") # lots of fusion, some mulu/kumulu
    | INSERT_I + Aff('la')        + Gloss('3SG.FEM.OBL')    + Nat("(.*) to her") # well represented, relatively clean break. 
    | INSERT_I + Aff('lɨna')        + Gloss('1PL.OBL')        + Nat("(.*) to us") # well represented
    | INSERT_I + Aff('lɨkumɨ')    + Gloss('2PL.MASC.OBL')     + Nat("(.*) to you") # 20? looks ok
    | INSERT_I + Aff('lɨnɨ')    + Gloss('2PL.FEM.OBL')      + Nat("(.*) to you") # almost always involves ə -> ɨ on stem, l could be part of stem
    | INSERT_I + Aff('lomɨ')    + Gloss('3PL.MASC.OBL')     + Nat("(.*) to them") # almost always lə -> lom on stem. 
    | INSERT_I + Aff('lənɨ')      + Gloss('3PL.FEM.OBL')      + Nat("(.*) to them") + Cost("XXXX") # relatively clean break when occurs.
                                                      # but lots of false positives with lə+n
    | NULL )

# Additional forms need entering. 
PRONCLITIC_OBJ = (
      INSERT_I +  Aff('ni')     + Gloss('1SG.OBJ')        + Nat("(.*) me") 
    | INSERT_I +  Aff('ka')     + Gloss('2SG.MASC.OBJ')   + Nat("(.*) you")
    | INSERT_I +  Aff('ki')     + Gloss('2SG.FEM.OBJ')    + Nat("(.*) you")  # very few of them
    | INSERT_I +  Aff('jo')     + Gloss('3SG.MASC.OBJ')   + Nat("(.*) him")  # najo also frequent
    | INSERT_I +  Aff('ʔo')     + Gloss('3SG.MASC.OBJ')   + Nat("(.*) him") 
    | INSERT_I +  Aff('wo')     + Gloss('3SG.MASC.OBJ')   + Nat("(.*) him")  # lots of kɨwo
    | INSERT_I +  Aff('ja')     + Gloss('3SG.FEM.OBJ')    + Nat("(.*) her")
    | INSERT_I +  Aff('wa')     + Gloss('3SG.FEM.OBJ')    + Nat("(.*) her")
    | INSERT_I +  Aff('ʔa')     + Gloss('3SG.FEM.OBJ')    + Nat("(.*) her") + Cost("XXXX") # Lots of fusion
    | INSERT_I +  Aff('na')     + Gloss('1PL.OBJ')        + Nat("(.*) us")   # lɨna also frequent
    | INSERT_I +  Aff('kumɨ')    + Gloss('2PL.MASC.OBJ')     + Nat("(.*) you")   # lɨkum also common
    | INSERT_I +  Aff('kɨnɨ')    + Gloss('2PL.FEM.OBJ')      + Nat("(.*) you")   # **0** tokens! Huh. 
    | INSERT_I +  Aff('jomɨ')    + Gloss('3PL.MASC.OBJ')     + Nat("(.*) them")   # Oh dear. jə/wə -> jom. MESSY. 
    | INSERT_I +  Aff('ʔomɨ')    + Gloss('3PL.MASC.OBJ')     + Nat("(.*) them")   # Likewise. ʔə -> ʔom. No clean boundary. 
    | INSERT_I +  Aff('jənɨ')      + Gloss('3PL.FEM.OBJ')      + Nat("(.*) them") + Cost("XXXX")
                                    # infrequent. Most string matches are false positives: j+ən
    | NULL )     
    

PREP = ( Aff('bɨ')            + Gloss('PREP') + Nat("with (.*)") 
        | Aff('nɨ')            + Gloss('PREP') + Nat("for (.*)") 
          | NULL )

# ʔɨ ʔɨtɨ ʔɨnɨ ʔɨtə
# These accompany internal vowel change and therefore did not help recall at all, except for ?i
# But should still be important to chop them off. 
VDERIV_PREF = ( INSERT_I + Aff('ʔɨtɨ') + Gloss('REL') + Nat("which (.*)") 
             | INSERT_I + Aff('ʔɨnɨ')   + Gloss('1PL.REL') + Nat("which (.*)") 
             | INSERT_I + Aff('ʔɨtə')   + Gloss('PASS') + Nat("which was (.*)-ed") 
             | INSERT_I + Aff('ʔɨ')   + Gloss('PRES') + Nat("(.*)")  # Not clear if indep. pref, may overgenerate -> HELPS! 
                                 # ʔɨfətɨwa እየ ʔɨjə ’ǝfätwa ’ǝyyä 'I like her'.  
             | NULL )

CASE_SUF = ( INSERT_I + Aff('nɨ')            + Gloss('ACC') + Nat("(.*)-OBJ") + Cost("XXXXXXXXXXXX") # bigger cost than 'and'
           | NULL )

CONJ_SUF = ( INSERT_I + Aff('wɨn')   + Gloss('CONJ') + Nat("and also (.*)") # Clausal; attaches to verb. Final ɨ omitted for now. Post-C allomorph?
    | INSERT_I + Aff('nɨ')            + Gloss('CONJ') + Nat("(.*) and")  + Cost("XXXXXXXXXX") # NP conjunction! lower cost than 'ACC' 
    | NULL )

ADJECTIVAL  = ( Aff('awi')   + Gloss('ADJ') + Nat("(.*)-ian") # in ሰኔጋላዊ səneɡalawi 'A Senegalese' Not sure if adj
    | Aff('wɨjanɨ') + Gloss('ADJ') + Nat("(.*)")    # in ኤርትራውያን ʔerɨtɨrawɨjan Not at all sure it's adjectival
    | NULL )   

Mutate = lambda x, y :  Tex(y) + Truncate(x, Tex) 
MERGE =  ( Mutate('kɨʔa', 'kə') | Mutate('mɨʔa', 'mə') | Mutate('zɨʔa', 'zə')
        | Mutate('bɨʔa', 'bə') | Mutate('nɨʔa', 'nə')
        | NULL) 


# These files list fully parsed entries. 
dict_preparsed = [dict_path+"IL5_PREPARSED_hornmorpho.tsv", dict_path+"IL5_PREPARSED.tsv"] # order! 
preparsed = process_preparsed_dict(dict_preparsed)

# Below are dictionary files. First two fields are absolutely necessary: eng_definition, tir_word. 
dict_list = [dict_path+"IL5_dictionary_1.txt", dict_path+"IL5_dictionary_2.txt",
             dict_path+"IL5_dictionary_3_SUPPL.txt", dict_path+"tir_gaz.txt"]

ROOT      = Lookup(dict_list, Text/Breakdown/Lemma, Gloss/Nat)
#ROOT = Guess(Lem)   # SWITCH FOR GRAMMAR BUILDING!! 

# REL is outer to NEG, which is taken care of by Mutate('zɨʔa', 'zə')
# zǝ- + ’ay- : zäy- , e.g., ዘይንደሊ zəjɨnɨdəli 'which we don't want'

CLITICS = (POSS | PRONCLITIC_OBLIQ | PRONCLITIC_OBJ)
MATRIX = (TENSE|PREP|VDERIV_PREF) >> ROOT << NUMBER << CLITICS << NEG << (CASE_SUF|ADJECTIVAL|CONJ_SUF)
PARSER = MERGE >> (REL|CONJ_PREF) >> MATRIX << TRUNC_FINAL_I 
#PARSER = (REL|CONJ) >> MATRIX 
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

    def sortparse(p):
        getcost = lambda x: len(x[u'cost'])
        return sorted(p, key=getcost)
        
    testprint_ipa = lambda x: print(json.dumps(sortparse(PARSER.parse(x)), ensure_ascii=False), "\n")
    
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
    print(g2p('ኢና'))
    testprint_ipa('ʔɨsɨraʔelɨn')
    testprint_ipa('jasin')
    testprint_ipa('ʕarafat')
    wd1 = 'ʔɨsɨraʔelɨn'
    wd2 = 'jasin'

    

    ################ BELOW FUNCTIONS & NOTES FOR DEVELOPMENT PURPOSES ONLY...
    ### YEP IT'S MESSY. I CAN WRITE PRETTY/CLEAN CODE, I SWEAR. GIVEN AMPLE TIME THAT IS.   

    # 1218 ከኣ kəʔa  'et' (and) in French
    # no other french dictionary lookup was successful among these freq items not captured:
    ##814 ነዚ nəzi ["PREP-ʔazi", "nəzi", "nɨʔazi"]
    ##641 ነው nəw ["PREP-ʔaw", "nəw", "nɨʔaw"]
    ##589 ምዃኑ mɨxʷanu ["CONJ-xʷan-3SG.MASC.POSS", "CONJ-xʷanu", "mɨxʷan-3SG.MASC.POSS", "mɨxʷanu"]
    ##547 ህግደፍ hɨɡɨdəf ["hɨɡɨdəf"]
    ##462 አብ ʔəb ["ʔəb"]
    ##407 ኸኣ xəʔa ["xəʔ-3SG.FEM.POSS", "xəʔa", "xə-3SG.FEM.OBJ"]
    ##405 ኢሳያስ ʔisajas ["ʔisajas"]
    ##371 ሃገርና haɡərɨna ["haɡərɨ-1PL.POSS", "haɡərɨ-1PL.OBJ", "haɡərɨn-3SG.FEM.POSS", "haɡərɨna"]
    ##365 እሞ ʔɨmo ["ʔɨmo"]
    ##353 ሰልፊ səlɨfi ["səlɨfi"]
    ##309 ደኣ dəʔa ["dəʔ-3SG.FEM.POSS", "dəʔa", "də-3SG.FEM.OBJ"]

    
    returngloss = lambda x: json.dumps(parse(x, 'gloss'), ensure_ascii=False)

    import re
    # eng_gloss = re.compile(r'.*\"[A-Za-z\-\.]+\".*')
        # ^^ Python re: I hate you. "." is screwy: Doesn't match "faith-3PL.MASC.POSS", "religion-3PL.MASC.POSS",
    eng_gloss = re.compile(r'.*\"[A-Za-z\-]+(.[A-Z][A-Z]+)*\".*')
    def eng_found(g, k=''):
        if k == g[2:-2].replace("\\","") or eng_gloss.search(g): return "LOOKUP_TRUE"
        else: return "LOOKUP_FALSE"

"""
    horse = "fərəs"
    horses = "ʔafɨrasə"
    ear = "ʔɨzɨni"
    ears = "ʔaʔɨzan"
    ROOT2 = Tex('frs') + Gloss('horse')
    PLU_PATTERN = Tex("ʔa(.)ɨ(.)a(.)ə") + Gloss("PLU") | Tex("(.)ə(.)ə(.)") + Gloss("SG")
    PARSER2 = ROOT2 << PLU_PATTERN
>>> PARSER2.parse(horse)
[{u'gloss': u'horse-SG'}]
>>> PARSER2.parse(horses)
[{u'gloss': u'horse-PLU'}]
>>> 
"""

def testfile(f, printall=True):
    wlines = open(f, encoding="utf8").readlines()
    for wline in (wlines):
        if wline.startswith("#"): continue
        w = wline.strip().split()[0]
        print(w, g2p(w))
        g = returngloss(w)
        if (eng_found(g) == 'LOOKUP_FALSE' or printall):
            testprint_ipa(g2p(w))    

def testit():
    testfile("testit.txt")         

success = []
def test1000(num=1000, quiet=True, flip=False):
    lines = open("../mor/count_tir_gloss.SORTED2.top1K.txt", encoding="utf8").readlines()
    words = [tuple(x.split()[:3]) for x in lines]
    count = 0
    tokcount = 0
    for (c, w, ipa)  in words[:num]:
        g = returngloss(w)
        if eng_found(g) == 'LOOKUP_TRUE' or ipa in preparsed:
              if not flip and not quiet: print(c, w, ipa, g)
              count += 1
              tokcount += int(c)
              success.append(ipa)
        else:
            if flip and not quiet: print(c, w, ipa, g)
    print("%d new types" % count)
    print("adds up to total %d tokens, %.2f percent of total tokens." % (tokcount, float(tokcount)/572497 * 100))

def process_freq():
    import pickle
    f = open('count_tir_gloss_list.p', 'rb')
    freqdat = pickle.load(f)
    f.close()

    freq, keys, ipas = freqdat[0], freqdat[1], freqdat[2]

    k_glossed = [(k, returngloss(k)) for k in keys]
    glossed = [g for (k,g) in k_glossed] 
    lookupout = [eng_found(g,k) for (k,g) in k_glossed]
    print('all 5 columns prepared.')
    
    allzip = zip(freq, keys, ipas, lookupout, glossed)  # high count first, but still sorted by key
    print('allzip file processed.')
    
    outfile = 'count_tir_gloss.v2.txt'
    alllines = ["%s\t%s\t%s\t%s\t%s\n" % x for x in allzip]
    fout = open(outfile, 'w', encoding="utf8")
    fout.writelines(alllines)
    fout.close()                                
    print(outfile, 'file written out.')
              

def testwiki(): 
    wiki_lines = open('testwiki.txt', encoding='utf8').readlines()
    wiki_lines = [l for l in wiki_lines if not l.startswith("#")]
    wiki_words = ' '.join(wiki_lines).split()

    for w in wiki_words:
        g = returngloss(w)
        print(w, g2p(w), g, sep="\t")


    # 572497 all tokens, 113816 all types
    # 78356 hapaxes --> 13.68% of all tokens, 68.84% of all types 
    # 35460 2+ types  --> 31.16% of all types. Totalling 494141 tokens. 
      # v1
        # 7323 successful, covers 288850 tokens.  (50.4%)
        # 28137 unsucessful, covers 205291 tokens. 
            # 1000 top types total 87137 tokens, which is (15.2% of tokens).
      # v2
        # 7867 successful, covers 302121 tokens. (52.77%)
        # 27593 unsuccessful, covers 192020 tokens. 

    # top 500 LOOKUP_FALSE token count is 69964
    # top 1000: LOOKUP_FALSE token count 69964

    # 114327 --> 12093 if counting 5 >  
    #wordf_5min = {w:wordf[w] for w in wordf if wordf[w] >= 5}

    # TOP1000 v1 --> v2
    # 60 new types
    # adds up to total 11026 tokens, 1.93 percent of total tokens.
    
    # from v2 --> : 
    # 406 new types (out of top 1000! Not bad.) 
    # adds up to total 41432 tokens, 7.24 percent of total tokens.

    # after spending hour+ cleaning up object clitic rules:
    # 409 new types
    # adds up to total 41575 tokens, 7.26 percent of total tokens. HARHARHAR

    # added tə jɨ (PERF -- 3 new types), mɨ, ki (conj -- 8 new types, all mɨ)
    # 420 new types
    # adds up to total 42160 tokens, 7.36 percent of total tokens.
    #          <-- yay for progress!

    # added *4* definite articles x their "for" and "with" variety into PREPARSED
    # 423 new types  
    # adds up to total 43281 tokens, 7.56 percent of total tokens.

    # after adding bi ni prepositions:
    # 456 new types
    # adds up to total 45496 tokens, 7.95 percent of total tokens.


# after fixing final n: 
# 467 new types
# adds up to total 46639 tokens, 8.15 percent of total tokens.

# many suffixes ended with -n, which only works if the word ends there!
# so, added ɨ in.
# 479 new types
# adds up to total 47124 tokens, 8.23 percent of total tokens.

# After implementing the merge rule. 
# 485 new types
# adds up to total 47891 tokens, 8.37 percent of total tokens.

# After manually entering some top-ranking words into the SUPPL and PREPARSED files. 
# 493 new types
# adds up to total 51598 tokens, 9.01 percent of total tokens.
#    <-- Well, the files were copied over to the two servers, so technically in v4. 

# After entering a top-ranking word ('and') and adding win ('and) suffix:
# 496 new types
# adds up to total 52899 tokens, 9.24 percent of total tokens.

# After fixing trailing , eng tokens (74 or so) in dictionary 2:
# 496 new types
# adds up to total 52899 tokens, 9.24 percent of total tokens.
# no change. oh well.

# After adding # ʔɨ ʔɨtɨ ʔɨnɨ ʔɨtə
# only ʔɨ helped, as others seem to accompany internal vowel changes
# 503 new types
# adds up to total 53519 tokens, 9.35 percent of total tokens.

# After instituting INSERT_I and fixing -n -at allomorph issues. 
# 528 new types
# adds up to total 55166 tokens, 9.64 percent of total tokens.
