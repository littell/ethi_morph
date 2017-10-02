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

Text = Spaced('text')
Aff = Text & Breakdown
Def = Spaced("definition")
Nat = Spaced("natural")
Cost = Concatenated("cost")
Lem = Text & Breakdown & Gloss & Lemma & Def & Nat

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

@memoized
def get_freq_dist():
    freq = FreqDist()
    freq.update(brown.words())
    return freq

@memoized
def get_g2p(lang):
    epi = epitran.Epitran(lang)
    return epi.trans_delimiter

@memoized
def get_dictionary(dict_directory, lookup_node='LEMMA', definition_node='GLOSS'):
    l1_to_l2 = defaultdict(list)
    l2_to_l1 = defaultdict(list)
    g2p = get_g2p("amh-Ethi")
    
    for llf_file in glob.glob(os.path.join(dict_directory, "*.llf.xml")):
        tree = ET.parse(llf_file)
        for entry in tree.xpath(".//ENTRY"):
            try: 
                ipa = entry.xpath(".//" + lookup_node + "/text()")[0]
                ipa = g2p(ipa)
            except:
                log_error("Cannot find pronunciation for " + "; ".join(entry.xpath(".//WORD/text()")) + " in " + llf_file)
                ipa = ''
            for definition in entry.xpath(".//" + definition_node + "/text()"):
                for subdef in definition.split(","):
                    subdef = subdef.strip()
                    l1_to_l2[ipa].append(subdef)
                    l2_to_l1[subdef].append(ipa) 
    return l1_to_l2
    
class Lookup(Parser):

    def __init__(self, child, directory, channel=None, output_channel=None):
        self.child = child
        self.dictionary = get_dictionary(directory)
        self.channel = channel
        self.output_channel = output_channel
        self.freqDist = get_freq_dist()
        self.engWords = self.freqDist.N()
    
    @memoized
    def __call__(self, input, input_channel=None, leftward=False):
        results = set()
        for output, remnant in self.child(input, input_channel, leftward):
            text = output[self.channel.name]
            text = text.strip()
            if text in self.dictionary:
                #print("found it: %s" % text)
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

NEG = (
      Aff('a l')            + Gloss('NEG')              + Nat("/not .*/") 
    | Aff('a')              + Gloss('NEG')              + Nat("/not .*/")           + Cost("XXX")
    | NULL
)

ENCLITIC = (
      Aff('a')              + Gloss('DISC')                                         + Cost("XX") 
    | Aff('m')              + Gloss('neither')          + Nat("/neither .*/")       + Cost("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX") 
    | Aff('? m')            + Gloss('neither')          + Nat("/neither .*/")
    | Aff('? m a')          + Gloss('as_for')           + Nat("/as for .*/") 
    | Aff('m a')            + Gloss('as_for')           + Nat("/as for .*/")        + Cost("X") 
    | Aff('? s')            + Gloss('as_for')           + Nat("/as for .*/") 
    | Aff('s')              + Gloss('as_for')           + Nat("/as for .*/")        + Cost("X")
    | Aff('? n a')          + Gloss('because')          + Nat("/because .*/") 
    | Aff('n a')            + Gloss('because')          + Nat("/because .*/") 
    | NULL
)

PREP = (
      Aff('b ?')            + Gloss('by')               + Nat("/by .*/")
    | Aff('?')              + Gloss('at')               + Nat("/at .*/")            + Cost("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX") 
    | Aff('l ?')            + Gloss('for')              + Nat("/for .*/")
    | Aff('k ?')            + Gloss('from')             + Nat("/from .*/")
    | Aff('t ?')            + Gloss('from')             + Nat("/from .*/")
    | Aff('j ?')            + Gloss('of')               + Nat("/of .*/")
    | NULL
)

NUMBER = (
      Aff('o t??')          + Gloss('PL')               + Nat("/multiple .*/")
    | Aff('w o t??')        + Gloss('PL')               + Nat("/multiple .*/")
    | Aff('j o t??')        + Gloss('PL')               + Nat("/multiple .*/")
    | NULL
)

DEFINITENESS = (
      Aff('w a')            + Gloss('DEF.F')            + Nat("/the .*/") 
    | Aff('i t u')          + Gloss('DEF.FEM')          + Nat("/the .*/") 
    | Aff('u')              + Gloss('DEF')              + Nat("/the .*/")           + Cost("X") 
    | Aff('w ?')            + Gloss('DEF.MASC')         + Nat("/the .*/") 
    | Aff('w')              + Gloss('DEF.PL')           + Nat("/the multiple .*/")  + Cost("X")
    | NULL
)

POSS = (
      Aff('e')              + Gloss('1SG.POSS')         + Nat("/my .*/")            + Cost("XX") 
    | Aff('h')              + Gloss('2SG.MASC.POSS')    + Nat("/your .*/")          + Cost("XX") 
    | Aff('? h')            + Gloss('2SG.MASC.POSS')    + Nat("/your .*/")
    | Aff('? ?')            + Gloss('2SG.FEM.POSS')     + Nat("/your .*/")
    | Aff('u')              + Gloss('3SG.MASC.POSS')    + Nat("/his .*/")           + Cost("XX")
    | Aff('? a')            + Gloss('3SG.FEM.POSS')     + Nat("/her .*/")
    | Aff('a t?? ? n')      + Gloss('1PL.POSS')         + Nat("/our .*/")
    | Aff('a t?? ? h u')    + Gloss('2PL.POSS')         + Nat("/your .*/")
    | Aff('a t?? ? w ?')    + Gloss('3PL.POSS')         + Nat("/their .*/")
    | Aff('w o')            + Gloss('2.POL.POSS')       + Nat("/your .*/")
    | Aff('a t?? ? w ?')    + Gloss('3.POL.POSS')       + Nat("/their .*/")
    | NULL
)

CASE = (
      Aff('n')              + Gloss('ACC') 
    | Aff('n ?')            + Gloss('ACC') 
    | Aff('? n')            + Gloss('ACC') 
    | Aff('? n ?')          + Gloss('ACC') 
    | NULL
)

ROOT        = Guess(Lem)
LOOKUP_ROOT = Lookup(ROOT, ".", Def, Def & Nat)
WORD        = LOOKUP_ROOT << NUMBER << DEFINITENESS << POSS << CASE
PHONWORD    = WORD << ENCLITIC
PARSER      = PREP >> PHONWORD

##############################
#
# CONVENIENCE FUNCTIONS
#
##############################

@memoized
def parse(word, representation_name="lemma"):
    g2p = get_g2p("amh-Ethi")
    ipa = g2p(word)
    parses = PARSER.parse(ipa)
    if not parses:
        print("Warning: cannot parse %s (%s)" % (word, ipa))
        parses = [{representation_name:ipa,"cost":""}]
    parses.sort(key=lambda x:len(x["cost"]) if "cost" in x else 0)
    return [x[representation_name].replace(' ', '') 
                    if representation_name in ["lemma","breakdown"]
                    else x[representation_name]
                    for x in parses]

@memoized
def best_parse(word, representation_name="lemma"):
    return parse(word, representation_name)[0]

if __name__ == '__main__':
    # just for testing.  to use this file, import it as a library and call parse() 
    with open("text-output.txt", "w", encoding="utf-8") as fout:
        testprint = lambda x: print(json.dumps(parse(x, "natural"), indent=2, ensure_ascii=False), file=fout)
        testprint('?????')
        testprint('????')
        testprint('????')
        testprint('???')
        testprint('????')
        testprint('????')
        testprint('????')
        testprint('?????')
        testprint('????????')
        testprint('??????')
        testprint('?????')
        
