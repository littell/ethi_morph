#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import re, collections, functools, json
from copy import deepcopy
from argparse import Namespace

################################
#
# Utility classes
#
################################

class memoized(object):
   '''Decorator. Caches a function's return value each time it is called.
   If called later with the same arguments, the cached value is returned
   (not reevaluated).
   '''
   def __init__(self, func):
      self.func = func
      self.cache = {}
   def __call__(self, *args):
      #if not isinstance(args, collections.Hashable):
         # uncacheable. a list, for instance.
         # better to not cache than blow up.
         # return self.func(*args)
      if args in self.cache:
         return self.cache[args]
      else:
         value = self.func(*args)
         self.cache[args] = value
         return value
   def __repr__(self):
      '''Return the function's docstring.'''
      return self.func.__doc__
   def __get__(self, obj, objtype):
      '''Support instance methods.'''
      return functools.partial(self.__call__, obj)
      
        
class HashableDict(dict):
    
    def __hash__(self):
        return hash(tuple(sorted(self.items())))
        
    def __lshift__(self, other):
        result = HashableDict()
        #for key in self.keys() + other.keys():
        for key in list(self) + list(other):
            if key in result:
                continue
            if key not in self:
                result[key] = other[key]
            elif key not in other:
                result[key] = self[key]
            else:
                try:
                    result[key] = self[key] >> other[key]
                except TypeError:
                    print("Cannot concatenate %s %s and %s %s" % (type(self[key]), self[key], type(other[key]), other[key]))
                    result[key] = 'ERROR'
                    
        return result
        
    def __rshift__(self, other):
        result = HashableDict()
        #for key in self.keys() + other.keys():
        for key in list(self) + list(other):
            if key in result:
                continue
            if key not in self:
                result[key] = other[key]
            elif key not in other:
                result[key] = self[key]
            else:
                result[key] = self[key] << other[key]
        return result    
    
             
        
##################################
#
# CHANNELS
#
##################################
       
class Channel(object):   
        
    def __init__(self, name):
        self.name = name
        
    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))
        
    def __call__(self, str):
        return make_default_parser(str, self)
        
    def __str__(self):
        return self.name
        
    def __repr__(self):
        return str(self)
        
    def __and__(self, other):
        return ChannelSequence(self, other)
        
    def __contains__(self, item):
        return False
        
    def __le__(self, other):
        return self == other or self in other
        
    def __iter__(self):
        yield self
        
    def __len__(self):
        return 1
        
    def typIsStr(self):
        return isinstance(self.typ(), unicode)
        
    def join(self, others):
        return self.typ( self.typ().delimiter().join(others) )
    
class ChannelSequence(Channel):

    def __init__(self, l_child, r_child):
        self.l_child = l_child
        self.r_child = r_child
        
    def __hash__(self):
        return hash(str(self))
        
    def __call__(self, str):
        return self.l_child(str) + self.r_child(str)
    
    def __le__(self, other):
        return self.l_child <= other and \
               self.r_child <= other  
        
    def __eq__(self, other):
        return self <= other and other <= self
        
    def __contains__(self, item):
        return item == self.l_child or \
               item in self.l_child or \
               item == self.r_child or \
               item in self.r_child
               
    def __str__(self):
        return "%s+%s" % (self.l_child, self.r_child)
   
    def __iter__(self):
        for x in self.l_child:
            yield x
        for y in self.r_child:
            yield y
            
    def __len__(self):
        return len(self.l_child) + len(self.r_child)
    
    def typIsStr(self):
        return self.l_child.typIsStr() and self.r_child.typIsStr()
        
        
class AbstractStr(unicode):
    ''' This is a subclass of str that string channels' typs descend from; it defines
        some default behavior for concatenation, testing for prefixation/suffixation, etc. '''

    def __lshift__(self, other):
        if self.is_pattern():
            return self.replacePattern(other)
        if other.is_pattern():
            return type(self)("/%s%s%s/" % (self, self.delimiter(), other[1:-1]))
        return type(self)("%s%s%s" % (self, self.delimiter(), other))
        
    def __rshift__(self, other):
        if other.is_pattern():
            return other.replacePattern(self)
        if self.is_pattern():
            return type(self)("/%s%s%s/" % (self[1:-1], self.delimiter(), other))
        return type(self)("%s%s%s" % (self, self.delimiter(), other))
        
    def endsWith(self, other):
        comparison_form = self.rstrip(self.delimiter())
        return comparison_form.endswith(other)
    
    def startsWith(self, other):
        comparison_form = self.lstrip(self.delimiter())
        return comparison_form.startswith(other)
    
    def hasPrefix(self, other):
        if self == other:
            return True
        pref = self[:len(other)+len(self.delimiter())]
        return pref == other + self.delimiter()
        
    def hasSuffix(self, other):
        if self == other:
            return True
        suf = self[-len(other)-len(self.delimiter()):]
        return suf == self.delimiter() + other

    def stripPrefix(self, other):
        assert(self.hasPrefix(other))
        if self == other:
            return type(self)('')
        return Concatenated.typ(self[len(other)+len(self.delimiter()):])
    
    def stripSuffix(self, other):
        assert(self.hasSuffix(other))
        if self == other:
            return type(self)('')
        return type(self)(self[:-len(other)-len(self.delimiter())])

    def is_pattern(self):
        return self[:1] == '/' and self[-1:] == '/'
        
    def replacePattern(self, input):
        # self is the pattern, input is what goes into it
        
        if not hasattr(self, 'non_parse_regex'):
            pattern = self[1:-1] if self.is_pattern() else self
            patternFinder = re.compile(r"\.[\+\?\*]?")
            parenser = lambda x:"(%s)"%x.group()
            parse_pattern = patternFinder.sub(parenser,pattern)
            parse_regex = re.compile(parse_pattern + r"$")
            non_parse_matches = patternFinder.findall(pattern)
            non_parse_matches = ["(" + m + ")" for m in non_parse_matches]
            non_parse_pattern = self.delimiter().join(non_parse_matches)
            self.non_parse_regex = re.compile(non_parse_pattern)
        
            numberGenerator = generateGroup()
            numberer = lambda x:next(numberGenerator)
            self.outputPattern = patternFinder.sub(numberer,pattern)
        
        text_out = self.non_parse_regex.sub(self.outputPattern, input, count=1)
        return type(self)(text_out)
        
#######################################
#
# PARSERS
# 
########################################

class Parser(object):
    
    def __init__(self, channel=None):
        self.channel = channel
        
    def get_channel(self):
        return self.channel
        
    def _is_trivial(self, input_channel):
        return not(set(self.get_channel()) & set(input_channel))
    
    def __lshift__(self, other):
        assert(isinstance(other, Parser))
        return RightwardSequence(self, other)
        
    def __rshift__(self, other):
        assert(isinstance(other, Parser))
        return LeftwardSequence(self, other)
        
    def __add__(self, other):
        assert(isinstance(other, Parser))
        return Sequence(self, other)
        
    def __sub__(self, other):
        assert(isinstance(other, Channel))
        return Trim(self, other)
        
    def __or__(self, other):
        return Choice(self, other)
        
    def __invert__(self):
        return Negation(self)
        
    def _trivial_parse(self, input, input_channel, leftward=False):
        return set([(HashableDict(), input)])  # a trivial success
        
    def _nontrivial_parse(self, input, input_channel, leftward=False):
        return set([(HashableDict(), input)])  # a trivial success
        
    
    def __call__(self, input, input_channel=None, leftward=False):
    
        if input_channel == None:  # assign it here rather than in the function definition
            input_channel = DEFAULTS.Text   # in case the library user redefines the concatenation type of Text
            
        if self._is_trivial(input_channel):
            return self._trivial_parse(input, input_channel, leftward)
            
        return self._nontrivial_parse(input, input_channel, leftward)
        
        
    
    def parse(self, s, input_channel=None):
        ''' Parse the str into a list of outputs.  A wrapper around __call__ that discards
            incomplete parse outputs (that is, ones that have a remainder) '''
        
        if input_channel == None:  # assign it here rather than in the function definition
            input_channel = DEFAULTS.Text   # in case the library user redefines the concatenation type of Text
            
        if len(input_channel) > 1:
            print("ERROR: parse method requires a simple data type; %s is complex." % input_channel)
            return []
        if not input_channel.typIsStr():
            print("ERROR: Cannot parse a non-string data type: %s" % input_channel)
            return []
            
        input = HashableDict()
        for input_channel in input_channel:
            input[input_channel.name] = input_channel.typ(s)
        parses = self(input, input_channel)
        return [output for output, remnant in parses if not remnant[input_channel.name]]
 
            
class LiteralParser(Parser):

    def __init__(self, pattern, channel=None):
        super(LiteralParser, self).__init__(channel)
        assert(len(channel)==1)
        self.pattern = channel.typ(pattern)
        self.output = HashableDict({channel.name:channel.typ(pattern)})
        
    def _trivial_parse(self, input, input_channel=None, leftward=False):
        return set([(self.output, input)])
        
    def _nontrivial_parse(self, input, input_channel=None, leftward=False):
        text = input[self.channel.name]
            
        hasAffix = text.hasPrefix if leftward else text.hasSuffix
        stripAffix = text.stripPrefix if leftward else text.stripSuffix
        
        if hasAffix(self.pattern):
            remnant = deepcopy(input)
            remnant[self.channel.name] = stripAffix(self.pattern)
            return set([(HashableDict(), remnant)])
        else:
            return set()
    
    
class Guess(Parser):

    def __init__(self, channel=None, output_channels=None):
        super(Guess, self).__init__(channel)
        self.output_channels = output_channels if output_channels else channel
    
    def _nontrivial_parse(self, input, input_channel=None, leftward=False):
        
        assert(len(input_channel)==1)
        
        results = set()
        text = input[input_channel.name]        

        hasAffix = text.hasPrefix if leftward else text.hasSuffix
        stripAffix = text.stripPrefix if leftward else text.stripSuffix
                
        for i in range(len(text)):
            remnant = deepcopy(input)
            substr = text[:i+1] if leftward else text[i:]
            stem = input_channel.typ(substr)
            if hasAffix(stem):
                remnant[input_channel.name] = stripAffix(stem)
                output = HashableDict()
                for output_channel in self.output_channels:
                    if output_channel != input_channel:
                        output[output_channel.name] = output_channel.typ(stem)
                results.add((output, remnant))
        return results

class BinaryCombinator(Parser):

    def __init__(self, l_child, r_child):
        self.l_child = l_child
        self.r_child = r_child
    
    def get_channel(self):
        return self.l_child.get_channel() & self.r_child.get_channel()

       
# class Unsequence(BinaryCombinator):
    # ''' An unsequence is a combination of parsers that are not necessarily executed in their written order; rather, a nontrivial parser
       # (one that consumes input) is executed before a trivial parser (one that consumes no input).  This exists because there are some
       # priority conflicts between parsers (especially Pattern parsers). 
       
       # If there is more than one nontrivial parser in a sequence A & B & C..., results may be different than one expects.  Generally, this
       # combinator should be used in sequences where only one parser is expected to be nontrivial.  Presumably, if you have two nontrivial
       # parsers, you expect them to be executed in a particular order, and should thus use combinators that enforce an order!'''
    
    # 
    # def __call__(self, input, input_channel=None, leftward=False):
            
        # l_child_is_trivial = self.l_child._is_trivial(input_channel)
        # r_child_is_trivial = self.r_child._is_trivial(input_channel)
        
        # if l_child_is_trivial and not r_child_is_trivial:
            # child1, child2 = self.r_child, self.l_child
        # elif not l_child_is_trivial and r_child_is_trivial:
            # child1, child2 = self.l_child, self.r_child
        # elif leftward:
            # child1, child2 = self.l_child, self.r_child
        # else:
            # child1, child2 = self.r_child, self.l_child
        
        # results = set()
        # for outputs1, remnant1 in child1(input, input_channel, leftward):
            # for outputs2, remnant2 in child2(remnant1, input_channel, leftward):
                # outputs = outputs1 >> outputs2 if leftward else outputs2 << outputs1
                # results.add((outputs, remnant2))
        # return results
        
        
class Sequence(BinaryCombinator):
    ''' A parser that executes its children in sequence, and applying the second to the remnant of the first.  The direction (left child first or right child first) depends on the value passed into the parameter leftward. '''

    
    def __call__(self, input, input_channel=None, leftward=False):
            
        child1 = self.l_child if leftward else self.r_child
        child2 = self.r_child if leftward else self.l_child
        
        results = set()
        for outputs1, remnant1 in child1(input, input_channel, leftward):
            for outputs2, remnant2 in child2(remnant1, input_channel, leftward):
                outputs = outputs1 >> outputs2 if leftward else outputs2 << outputs1
                results.add((outputs, remnant2))
        return results
            
class RightwardSequence(Sequence):
    ''' This is a sequence combinator that always executes right-to-left, regardless
        of the directionality of higher combinators. (That is to say, it ignores the
        passed-in value of the leftward parameter and always acts as if it's False.) '''
        
    
    def __call__(self, input, input_channel=None, leftward=False):
        return super(RightwardSequence, self).__call__(input, input_channel, False)  
  
class LeftwardSequence(Sequence):
    ''' This is a sequence combinator that always executes left-to-right, regardless
        of the directionality of higher combinators. (That is to say, it ignores the
        passed-in value of the leftward parameter and always acts as if it's True.)'''
    
    
    def __call__(self, input, input_channel=None, leftward=False):
        return super(LeftwardSequence, self).__call__(input, input_channel, True)
        
class Choice(BinaryCombinator):

    
    def __call__(self, input, input_channel=None, leftward=False):
        return self.l_child(input, input_channel, leftward) | self.r_child(input, input_channel, leftward)

        
class AssertParser(Parser):
    ''' An Assert parser asserts a predicate of the input at that stage 
        of the parse and failing (that is, returning set([])) if the predicate fails '''

    def __init__(self, pred, channel=None):
    
        if channel == None:  # assign it here rather than in the function definition
            channel = DEFAULTS.Text   # in case the library user redefines the concatenation type of Text
            
        self.channel = channel
        self.pred = pred
        
    def _is_trivial(self, input_channel):
        return True
        
    
    def __call__(self, input, input_channel=None, leftward=False):
            
        if self.channel.name not in input or not self.channel <= input_channel:
            return set([(HashableDict(), input)])
       
        text = input[self.channel.name]
        if not self.pred(text):
            return set()
            
        return set([(HashableDict(), input)])
        
class Delay(Parser):
    ''' A Delay allows you to make recursive grammars.  If you need to refer to a parser that you have not yet defined, you will get
        a NameError in Python.  To avoid this, you can refer to a label as Delay(lambda:X) rather than X. '''
        
    def __init__(self, parser):
        self.parser = parser
        
    def get_channel(self):
        return self.parser().get_channel()
        
    
    def __call__(self, input, input_channel=None, leftward=False):
        return self.parser()(input, input_channel)    
        
        
class Negation(Parser):

    def __init__(self, child):
        self.child = child
    
    def _is_trivial(self, input_channel):
        return self.child._is_trivial(input_channel)
    
    def get_channel(self):
        return self.child.get_channel()
        
    
    def __call__(self, input, input_channel=None, leftward=False):
        child_results = self.child(input, input_channel, leftward)
        if child_results:
            return set()
        return set([(HashableDict(), input)])
        
        
class NullParser(Parser):

    def __init__(self):
        super(NullParser, self).__init__([])
       
def generateGroup(x=0):
    while True:
        x += 1
        yield "\%s" % x

        
class PatternParser(Parser):

    def __init__(self, pattern, channel=None):
    
        if channel == None:
            channel = DEFAULTS.Text
        assert(len(channel)==1)
        
        strippedPattern = pattern
        if pattern.startswith("/") and pattern.endswith("/"):
            strippedPattern = pattern[1:-1]
       
        self.channel = channel
        self.inputPattern = strippedPattern
        
        patternFinder = re.compile(r"\.[\+\?\*]?")
        parenser = lambda x:"(%s)"%x.group()
        parse_pattern = patternFinder.sub(parenser,strippedPattern)
        self.parse_regex = re.compile(parse_pattern + r"$")
        
        non_parse_matches = patternFinder.findall(strippedPattern)
        non_parse_matches = ["(" + m + ")" for m in non_parse_matches]
        non_parse_pattern = self.channel.join(non_parse_matches)
        self.non_parse_regex = re.compile(non_parse_pattern)
        
        numberGenerator = generateGroup()
        numberer = lambda x:next(numberGenerator)
        self.outputPattern = patternFinder.sub(numberer,strippedPattern)
        
        self.output = HashableDict({
            self.channel.name:self.channel.typ("/"+strippedPattern+"/")
        })
        
    # def _trivial_parse(self, input, input_channel=None, leftward=False):
        # text_in = input[input_channel.name]
        # text_out = self.non_parse_regex.sub(self.outputPattern, text_in)
        # outputs = HashableDict({self.channel.name:self.channel.typ(text_out)})
        # return set([(outputs, input)])        
        
    def _trivial_parse(self, input, input_channel=None, leftward=False):
        return set([(self.output, input)])
        
    def _nontrivial_parse(self, input, input_channel=None, leftward=False):
        text_in = input[self.channel.name]
        match = self.parse_regex.match(text_in)
        if not match:
            return set()
        remnant = deepcopy(input)
        remnant[input_channel.name] = self.channel.join(match.groups())
        return set([(HashableDict(), remnant)])


class Trim(Parser):

    def __init__(self, child, channel):
        self.child = child
        self.channel = channel
        
    
    def __call__(self, input, input_channel=None, leftward=False):
    
        if input_channel == None:  # assign it here rather than in the function definition
            input_channel = DEFAULTS.Text   # in case the library user redefines the concatenation type of Text
            
        results = set()
        for child_output, child_remnant in self.child(input, input_channel, leftward):
            output = deepcopy(child_output)
            for channel in self.channel:
                if channel.name in output:
                    del output[channel.name]
            results.add((output, child_remnant))
        return results     
        
#####################################
#
# Convenience functions for channels
#
#####################################


def make_channel_from_delimiter(delim):

    class AnonymousChannel(Channel):
        class typ(AbstractStr):
            def delimiter(self):
                return delim
                
    return AnonymousChannel
    
def make_reverse_channel_from_delimiter(delim):

    class AnonymousChannel(Channel):
        class typ(AbstractMirroredStr):
            def delimiter(self):
                return delim
                
    return AnonymousChannel            
            
###############################
#
# Convenience functions
#
###############################

def make_default_parser(text, channels=None):
    if channels == None:
        channels = DEFAULTS.Text
    if text.startswith("/") and text.endswith("/"):
        return Pattern(text, channels)
    return Lit(text, channels)
    
def make_multichannel_parser(parser, pattern, channels=None):

    if channels == None:
        channels = DEFAULTS.Text

    result = None
    for channel in channels:
        p = parser(pattern, channel)
        result = p if not result else Unsequence(result, p)
    return result
        
        
def Lit(text, channels=None):
    if channels == None:
        channels = DEFAULTS.Text
    return make_multichannel_parser(LiteralParser, text, channels)
    
    
def Assert(pred, channel=None):

    if channel == None:  # assign it here rather than in the function definition
        channel = DEFAULTS.Text   # in case the library user redefines the concatenation type of Text
            
    return make_multichannel_parser(AssertParser, pred, channel)
        
def After(s, channel=None):
    pred = lambda x: x.endsWith(s)
    return Assert(pred, channel)
    
def Before(s, channel=None):
    pred = lambda x: x.startsWith(s)
    return Assert(pred, channel)

def Pattern(pattern, channels=None):

    if channels == None:  # assign it here rather than in the function definition
        channels = DEFAULTS.Text   # in case the library user redefines the concatenation type of Text
            
    return make_multichannel_parser(PatternParser, pattern, channels)

def Rap(pattern, root_channels=None, pattern_channels=None):

    if root_channels == None:
        root_channels = DEFAULTS.Lem
        
    if pattern_channels == None:
        pattern_channels = DEFAULTS.Text

    return Guess(root_channels) - pattern_channels << Pattern(pattern, pattern_channels)
    
    
NULL = NullParser()


######################################
#
# BUILT-IN CHANNELS
#
######################################

Concatenated = make_channel_from_delimiter("")
Spaced = make_channel_from_delimiter(" ")
Hyphenated = make_channel_from_delimiter("-")
Mirrored = make_channel_from_delimiter(" ")
        
Text = Concatenated("text")
Breakdown = Hyphenated("breakdown")
Lemma = Hyphenated("lemma")
Gloss = Hyphenated("gloss")
Citation = Hyphenated("citation")
Lem = Text & Breakdown & Lemma
Aff = Text & Breakdown    
    
DEFAULTS = Namespace(Text=Text, Lem=Lem)
   