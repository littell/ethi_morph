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
epi = epitran.Epitran("orm-Latn")
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
            #ipa = g2p(word)
            ipa = word     
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
#PARSER      = Lookup("orm_lexicon.txt", Tex/Mor/Lem, Glo/Cit/Nat)
LEMMA = Lookup("orm_lexicon_norm.txt", Tex/Mor/Lem, Glo/Cit/Nat)

##############################
#
# CONVENIENCE FUNCTIONS
#
##############################
@lru_cache(maxsize=1000)
def parse(word, representation_name="lemma"):
    ipa = g2p(word)
    
    parses = PARSER.parse(word.lower())
    #parses = PARSER.parse(ipa)
    if not parses:
        print("Warning: cannot parse %s (%s)" % (word, ipa))
        parses = [{representation_name:ipa,"cost":""}]
    parses.sort(key=lambda x:len(x["cost"]) if "cost" in x else 0)
    return [x[representation_name] for x in parses]
@lru_cache(maxsize=1000)
def best_parse(word, representation_name="lemma"):
    return parse(word, representation_name)[0]



VV = "(aa|ee|ii|oo|uu)"
V = "(a|e|i|o|u)"
C = "(b|c|ch|d|dh|f|g|h|j|k|l|m|n|ny|p|ph|q|r|s|sh|t|v|w|x|y|z)"

#LEMMA = Guess(Tex/Mor/Lem/Glo)

#VERB = PRE_VERB + VERB_ROOT + VOICE_EXTENSION + PERSON + PLURAL_TENSE + CASE

# Morpheme-boundary phonological changes
# Open things: Some assimilations to double consonants (tt, nn) may variably be written as single (t, n)?
NTexMor = lambda x : Tex/Mor(x) | After("r", Tex) + Tex("r" + x[1:]) + Mor(x) | (After("l",Tex) + Tex("l" + x[1:]) + Mor(x)) | Truncate("t", Tex) + Tex("n") + Tex/Mor(x) | Truncate("x", Tex) + Tex("n") + Tex/Mor(x) | Truncate("d", Tex) + Tex("n") + Tex/Mor(x) | Truncate("dh", Tex) + Tex("n") + Tex/Mor(x) | Truncate("s", Tex) + Tex("f") + Tex/Mor(x) 
TTexMor = lambda x: Tex/Mor(x) | After("(b|g|d)", Tex) + Tex("d" + x[1:]) + Mor(x) | After("(x|q)", Tex) + Tex("x" + x[1:]) + Mor(x) | Truncate("dh", Tex) + Tex("t") + Tex/Mor(x) | Truncate("s", Tex) + Tex("f") + Tex/Mor(x)



# Remove final vowel
RemoveFinalVowel = NULL | Truncate("a", Tex) | Truncate("e", Tex) | Truncate("i", Tex) | Truncate("o", Tex) | Truncate("u", Tex)


NOUN_STEM = LEMMA

NOUN_PLURAL = NULL | \
		RemoveFinalVowel + Tex/Mor("ota") + Glo("PL") + Nat("more than one (.*)") | \
		RemoveFinalVowel + TTexMor("tota") + Glo("PL") + Nat("more than one (.*)") | \
		RemoveFinalVowel + Tex/Mor("wan") + Glo("PL") + Nat("more than one (.*)") | \
		RemoveFinalVowel + Tex/Mor("en") + Glo("PL") + Nat("more than one (.*)") | \
		RemoveFinalVowel + Tex/Mor("an") + Glo("PL") + Nat("more than one (.*)") | \
		RemoveFinalVowel + Tex/Mor("le") + Glo("PL") + Nat("more than one (.*)") | \
		RemoveFinalVowel + Tex/Mor("yi") + Glo("PL") + Nat("more than one (.*)") | \
		RemoveFinalVowel + Tex/Mor("oti") + Glo("PL") + Nat("more than one (.*)") | \
		RemoveFinalVowel + Tex/Mor("oli") + Glo("PL") + Nat("more than one (.*)")
		

NOUN_DEF = NULL | \
		RemoveFinalVowel + Tex/Mor("icha") + Glo("M.DEF") + Nat("the (.*)") | \
		RemoveFinalVowel + TTexMor("ticha") + Glo("M.DEF") + Nat("the (.*)") | \
		RemoveFinalVowel + Tex/Mor("iti") + Glo("F.DEF") + Nat("the (.*)") | \
		RemoveFinalVowel + TTexMor("titi") + Glo("F.DEF") + Nat("the (.*)")

# -in might be a nominative case marker too
NOUN_CASE = NULL | \
		After(VV, Tex) + Tex/Mor("n") + Glo("NOM") | \
		RemoveFinalVowel + After("%s%s" % (V,C), Tex) + NTexMor("ni") + Glo("M.NOM") | \
		RemoveFinalVowel + After("%s" % C, Tex) + TTexMor("ti") + Glo("F.NOM") | \
		RemoveFinalVowel + After("%s" % C, Tex) + Tex/Mor("i") + Glo("NOM") | \
		After(C, Tex) + Glo("NOM") | \
		After(V) + Mor("GEN") + Nat("of (.*)") | \
		After(C) + Tex/Mor("i") + Glo("GEN") + Nat("of (.*)") | \
		Tex/Mor("f") + Glo("DAT") + Nat("to (.*)") | \
		Tex/Mor("f") + Glo("DAT") + Nat("to (.*)") | \
		After(C) + Tex/Mor("if") + Glo("DAT") + Nat("to (.*)") | \
		After(V) + Tex/Mor("dha") + Glo("DAT") + Nat("to (.*)") | \
		After(V) + Tex/Mor("dhaf") + Glo("DAT") + Nat("to (.*)") | \
		TTexMor("ti") + Glo("DAT") + Nat("to (.*)") | \
		After(V) + Tex/Mor("n") + Glo("INST") + Nat("with (.*)") | \
		Tex/Mor("n") + Glo("INST") + Nat("with (.*)") | \
		After(C) + Tex/Mor("in") + Glo("INST") + Nat("with (.*)") | \
		After(V) + Tex/Mor("tin") + Glo("INST") + Nat("with (.*)") | \
		Tex/Mor("tin") + Glo("INST") + Nat("with (.*)") | \
		After(V) + Tex/Mor("dhan") + Glo("INST") + Nat("with (.*)") | \
		TTexMor("ti") + Glo("LOC") + Nat("in (.*)") | \
		After(V) + Tex/Mor("dha") + Glo("ABL") + Nat("from (.*)") | \
		After(C) + Tex/Mor("i") + Glo("ABL") + Nat("from (.*)") | \
		TTexMor("ti") + Glo("ABL") + Nat("from (.*)")	
		
EMPHASIS = NULL | \
		Tex/Mor("tu") + Glo("EMPH")

ONLY = NULL | RemoveFinalVowel + Tex/Mor("uma") + Glo("ONLY") + Nat("only (.*)")

EVEN = NULL | Tex/Mor("le") + Glo("EVEN") + Nat("even (.*)")

COORD = NULL | \
	Tex/Mor("f") + Glo("AND") + Nat("and (.*)") | \
	Tex/Mor("fi") + Glo("AND") + Nat("and (.*)") | \
	Tex/Mor("s") + Glo("AS_WELL") + Nat("as well as (.*)") | \
	Tex/Mor("s") + Glo("AS_WELL") + Nat("as well as (.*)")

MYSTERY = NULL | \
		Tex/Mor("fa") + Glo("UNKNOWN")

NOUN = NOUN_STEM + NOUN_PLURAL + NOUN_DEF + ONLY + EMPHASIS + NOUN_CASE + EMPHASIS + EVEN + COORD + MYSTERY

PARSER = NOUN

#words = ["taatuun", "qilleensi", "jaballi", "afaan", "loltoonni", "namichi", "waantooti", "namichaa", "Caaltuu", "afaanii", "namichaa", "intalaaf", "sareef", "baruuf", "bishaaniif", "sareedhaa", "sareedhaaf", "Caaltuutti"]
pairs = []
#pairs = [("taatuun","taatuu-NOM"), ("qilleensi","qilleensa-NOM"), ("jaballi","jabala-M.NOM"), ("afaan","afaan-NOM"), ("loltoonni","loltoota-M.NOM"), ("namichi","namicha-NOM"), ("waantooti","waantoota-NOM"), ("namichaa","namicha-GEN"), ("Caaltuu","Caaltuu-GEN"), ("afaanii","afaan-GEN"), ("namichaa","namicha-DAT"), ("intalaaf","intala-DAT"), ("sareef","saree-DAT"), ("baruuf","baruu-DAT"), ("bishaaniif","bishaan-DAT"), ("sareedhaa","saree-DAT"), ("sareedhaaf","saree-DAT"), ("Caaltuutti","Caaltuu-DAT"), ("harkaan", "harka-INST"), ("halkaniin", "halkan-INST"), ("Oromotiin", "Oromo-INST"), ("yeroodhaan", "yeroo-INST"), ("bawuudhaan", "bawuu-INST"), ("Arsiitti", "Arsii-LOC"), ("harkatti", "harka-LOC"), ("guyyaatti", "guyyaa-LOC"), ("jalatti", "jala-LOC"), ("biyyaa", "biyya-ABL"), ("Finfinneedhaa", "Finfinnee-ABL"), ("Hararii", "Harar-ABL"), ("bunaatii", "bunaa-ABL"), ("manoota", "mana-PL"), ("hiriyoota", "hiriyaa-PL"), ("barsiisota", "barsiisaa-PL"), ("barsiisoota", "barsiisaa-PL"), ("waggaawwan", "waggaa-PL"), ("laggeen", "laga-PL"), ("ilmaan", "ilma-PL"), ("namicha", "nama-M.DEF"), ("muzicha", "muzii-M.DEF"), ("durbittii", "durba-F.DEF"), ("ilkaan", "ilka-PL"), ("waantoota", "waanta-PL"), ("guyyawwan", "guyyaa-PL"), ("gaarreen", "gaara-PL"), ("laggeen", "laga-PL"), ("mukkeen", "muka-PL"), ("waggottii", "waggaa-PL"), ("kitaabolii", "kitaaba-PL"), ("yunivarsitichaan", "yunivarsiti-DEF-GEN")]

#for pair in pairs:
#	parse = str(PARSER.parse(pair[0]))
#	if pair[1] not in parse:
#		print(pair[0], parse)

#print PARSER.parse("hidiin")
#print PARSER.parse("haattii")
#print PARSER.parse("duresii")
#print PARSER.parse("namnii")

if __name__ == '__main__':
    # just for testing.  to use this file, import it as a library and call parse() 
    with open("text-output.txt", "w", encoding="utf-8") as fout:
        testprint = lambda x: print(json.dumps(parse(x, "gloss"), indent=2, ensure_ascii=False), file=fout)
	#testprint("laggeen")	
	for pair in pairs:
		print(pair)
		testprint(pair[0])
	 
