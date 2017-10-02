#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import unicode_literals
from io import open
import argparse, glob, os
from progressbar import ProgressBar, Bar, AdaptiveETA, Percentage
from amh_morph import *
import epitran

g2p = epitran.Epitran("amh-Ethi").trans_delimiter

def ensure_dir(mydir):
    if not os.path.isdir(mydir):
        os.makedirs(mydir)

def go(inputDir, outputDir):
    filenames = glob.glob(os.path.join(inputDir, "*.orig.amh"))
    for filename in filenames:
        print("Processing %s" % filename)
            
    
        with open(filename,'r',encoding="utf-8") as fin:
            basename = os.path.basename(filename).split(".")[0]
            lemmaFilename = os.path.join(outputDir, basename + ".lemma.amh")
            glossFilename = os.path.join(outputDir, basename + ".gloss.amh")
            with open(lemmaFilename,'w', encoding="utf-8") as lemmaFout:
                with open(glossFilename,'w', encoding="utf-8") as glossFout:
                    lines = fin.readlines()
                    bar = ProgressBar(maxval=len(lines), poll=1, widgets=[
                        Bar('=', '[', ']'), ' ',
                        Percentage(), ' ',
                        AdaptiveETA()])
                        
                    for line in bar(lines):
                        lemmas = []
                        gloss = []
                        for word in line.split(" "):
                            ipa = g2p(word)
                            output = list(PARSER.parse(ipa))
                            output.sort(key=lambda x:len(x["cost"]) if "cost" in x else 0)
                            output = output[0] if output else {}
                            if "lemma" not in output or not output["lemma"]:
                                lemmas.append(ipa)
                            else:
                                lemmas.append(output["lemma"].replace(" ",""))
                            if "gloss" not in output or not output["gloss"]:
                                gloss.append(ipa)
                            else:
                                parts = output["gloss"].replace(" ","").split("-")
                                gloss += parts
                        lemmaFout.write(" ".join(lemmas) + "\n")
                        glossFout.write(" ".join(gloss) + "\n")
                        
                        
if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("inputDir", help="An input tab-separated file containing a 'token' row")
    argparser.add_argument("outputDir", help="A tab-separated file to hold the output.")
    args = argparser.parse_args()
    ensure_dir(args.outputDir)
    go(args.inputDir, args.outputDir)