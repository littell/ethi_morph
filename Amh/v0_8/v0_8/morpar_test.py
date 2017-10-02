#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from __future__ import print_function
from morpar import *


#############################
#
# START TESTS
#
#############################


print("STARTING ARABIC TEST")        

DEFAULTS.Lem = Text & Gloss & Breakdown & Lemma

PATTERN1 = Rap(".a.a.") + Gloss("V")
PATTERN2 = Rap(".i.a.") + Gloss("N")
VSUF = Aff("ed") + Gloss("PAST") | \
       Aff("ing") + Gloss("PROG") | \
       Aff("s") + Gloss("3SG-PRES") | \
       NULL 
NSUF = Aff("s") + Gloss("PLURAL") | NULL
PARSER = PATTERN1 << VSUF | PATTERN2 << NSUF

print(PARSER.parse("kitabs"))
print(PARSER.parse("ktb",Lemma))

print()
print("STARTING TAGALOG TEST")
ROOT = Guess(Lem)
INFIX = Aff("um") + Gloss("PRES") | Text("/.um.*/") + Breakdown("um") + Gloss("PASS") | \
        Aff("in") + Gloss("PRES") | Text("/.in.*/") + Breakdown("in") + Gloss("PRES") | \
        NULL
PARSER = INFIX >> ROOT
print(PARSER.parse("umadin"))
print(PARSER.parse("sumulat"))
print(PARSER.parse("sulat",Lemma))


print()
print("STARTING ENGLISH TEST")

Nat = Spaced("natural")

ROOT = Lem("jump") | Lem("mine")
SUF = After("e") + Aff("d") + Nat("/did .*/") | \
      ~After("e") + Aff("ed") + Nat("/did .*/")
PARSER = ROOT << SUF
print(PARSER.parse("jumped"))
print(PARSER.parse("mined"))
print(PARSER.parse("jumpd"))
print(PARSER.parse("mineed"))

Text = Spaced("text")
Citation = Spaced("citation")
Lem = Text & Lemma & Breakdown & Gloss & Citation & Nat
DEFAULTS.Text = Text
DEFAULTS.Lem = Lem

print()
print("STARTING SPACED ENGLISH TEST")

ROOT = Lem("j u m p") | Lem("m i n e")
SUF = After("e") + Aff("d") + Nat("/did .* verily/") | \
      ~After("e") + Aff("e d") + Nat("/did .* verily/")
PARSER = ROOT << SUF
print(PARSER.parse("j u m p e d"))
print(PARSER.parse("m i n e d"))
print(PARSER.parse("j u m p d"))
print(PARSER.parse("m i n e e d"))
print(PARSER.parse("did j u m p verily", Nat))

print()
print("STARTING SPACED ARABIC TEST")

ROOT = Guess(Lem)
PATTERN1 = Citation("/y i . . u ./") + Text("/. a . a ./") + Breakdown("a a") + Gloss("V")
PATTERN2 = Citation("/y i . . u ./") + Text("/. i . a ./") + Breakdown("a a") + Gloss("N")
VSUF = Aff("e d") + Gloss("PAST") | \
       Aff("i n g") + Gloss("PROG") | \
       Aff("s") + Gloss("3SG-PRES") | \
       NULL 
NSUF = Aff("s") + Gloss("PLURAL") | NULL
PARSER = ROOT << (PATTERN1 << VSUF | PATTERN2 << NSUF)

print(PARSER.parse("k a t a b s"))
print(PARSER.parse("y i k t u b", Citation))
print(PARSER.parse("k t b",Lemma))