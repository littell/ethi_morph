import time
from orm_morph import *


fi = open("/usr2/data/rmccoy/first2000.txt", "r")

lines = fi.readlines()

start = time.time()
for line in lines[:10]:
	parseNow = best_parse(line.strip(), "gloss")
#	parses = parse(line.strip(), "gloss")
#	
#	for parseGuy in parses:
#		print parseGuy
	
#	parse2 = parse(line.strip(), "breakdown")
#	for parseGuy in parse2:
#		print parseGuy
	
#	print ""
end = time.time()
print end - start

