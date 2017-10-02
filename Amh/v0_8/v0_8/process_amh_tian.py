#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import unicode_literals
from io import open
import argparse, glob, os, json, sys
from amh_morph_nat import *

with open("NI_sf_brief.json","r", encoding="utf-8") as fin:
    sfs = json.loads(fin.read())
    for sftype in sfs:
        for sf in sftype:
            text = sf["Text"]
            results = []
            for word in text.split():
                natgloss = best_parse(word, "natural")
                results.append(natgloss)
            sf["NatGloss"] = " ".join(results)
            
    with open("NI_sf_brief_for_Alan.json","w", encoding="utf-8") as fout:
        fout.write(json.dumps(sfs, ensure_ascii=False, indent=4))

