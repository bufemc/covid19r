#! /usr/bin/python3
#
# This script computes an estimate of the "reverse" basic reproduction
# number R of SARS CoV 2 for a country.
#
# Notes/Caveats:
#
# - "Reverse R" means that it is an estimate of the past reproduction
#   number of infectious cases that are needed to cause the cases seen at
#   a given day.
# - The approach taken by this script is not scientifically validated,
#   although it looks quite reasonable to me:
#   - We assume that the probability that somebody infects someone else
#     who is reported follows a binomial distribution which is slightly
#     skewed towards the future.
#   - Due to the way this is implemented, the numbers for the last three
#     days will thus slightly increase once new data becomes available! The
#     rationale for this is that cases reported on a given day could have
#     caused some of the cases reported on earlier days.
#   - An "infectious case" is an active case that has not been
#     recognized. Once a case has been discovered, we assume that this
#     person gets quarantined and will not infect others anymore. It will
#     still affect the reported numbers of the following days due to
#     diagnostic and reporting delays.
#   - To reduce statistical noise, the curve is smoothened using a 14
#     day running average. The reason for this is that the data of all
#     countries seems to exhibit a fair amount of statistical noise
#     and almost all show strong oscilations with a weekly cycle
#     ("weekend effect"). Both the raw and the smoothened
#     estimates of reverse R are included in the result data, though.
# - The curves produced here can at most be as good as the input data
#   for a given country. In particular, this means that they might be
#   quite significantly off if the respective country's data
#   aquisition system and/or testing system get overwhelmed.
# - We assume that all infectious cases will be reported
#   eventually. This is certainly not the case, but as long as the
#   ratio of undiscovered to total cases remains constant (it probably
#   doesn't, see previous bullet point), this should not matter.
# - For small numbers, the R factor is subject to noise and not very
#   significant in the first place. For example this happens for
#   Taiwan.
#
# TODO/IDEAS:
#
# - Add an estimate of the confidence intervals. This involves getting
#   a grip on the quality of the input data as well as considering the
#   total number of cases.
# - Add a "political advice" system: Given a level of acceptable risk,
#   produce a number of whether loosening or tightening restrictions
#   is advisable. Besides the user input of the allowable risk level
#   and the estimate of R, this involves considering the total active
#   case numbers per capita, the confidence intervall of the estimate
#   as well as the reporting delay. Only producing this on a weekly
#   basis would be a bonus.
import os
import sys
import datetime
import operator as op
from functools import reduce

country = "Germany"
if len(sys.argv) > 1:
    country = sys.argv[1]

def nChosek(n, k):
    k = min(k, n-k)
    numer = reduce(op.mul, range(n, n-k, -1), 1)
    denom = reduce(op.mul, range(1, k+1), 1)
    return numer / denom

# generate a binomially distributed kernel to distribute the new cases
# of a given day over the past and the future. be aware that this is
# basically handwaveing and I have no data whatsoever to back it
# up. IMO the curves look plausible, though.
numDaysInfectious = 10 # number of days a case has an effect on the
                       # number of reported cases
weightsOffset = -4 # first day a case has an influence on the reported
                   # numbers [days after an infection is reported]
k = 7 # specify the "center of infectiousness" of new cases w.r.t. the
      # report date. we set this slightly to the future, i.e., larger
      # than the negative weightsOffset [range: [0, 10]]

weightsList = []
sumWeights = 0.0
for i in range(0, numDaysInfectious + 1):
    p = i / float(numDaysInfectious)

    # use the binomial distribution. This is not based on any evidence
    # except for "looks reasonable to me"!
    weightsList.append(nChosek(numDaysInfectious, k) * p**k * (1 - p)**(numDaysInfectious - k))
    sumWeights += weightsList[-1]

# normalize the weights list
weightsList = list(map(lambda x: x/sumWeights, weightsList))

def boxFilter(data, n, offset=0):
    result = []

    for i in range(0, len(data)):
        sumValues = 0
        numValues = 0
        for j in range(max(0, int(i - n + offset)), min(len(data), int(i + offset + 1))):
            numValues += 1
            sumValues += data[j]

        result.append(sumValues/numValues)

    return result

dataSourceDir = "COVID-19/csse_covid_19_data/csse_covid_19_daily_reports"

filesList = []

for root, dirs, files in os.walk(dataSourceDir):
    for file in files:
        if not file.endswith(".csv"):
            continue

        filesList.append(file)

def fileNameToDateTime(fileName):
    dt = datetime.datetime.strptime(fileName, '%m-%d-%Y.csv')
    return dt
filesList.sort(key=fileNameToDateTime)

timeList = []
totalCases = []
deltaCases = []
for file in filesList:
    for curLine in open(dataSourceDir + "/" + file).readlines():
        fields = curLine.split(",")
        numCases = None
        if fields[3] == country and fields[2] == "":
            numCases = int(fields[7])
        elif country == "US":
            # as usual, things are done differently in the US: we need
            # to sum the number of cases for every ZIP code in the
            # file. Also, some data points like Cruise ships do not
            # have ZIP codes (we do not consider them for now)
            if fields[3] == country and fields[0] != "":
                numCases = int(fields[7])
            elif fields[1] == country:
                # before March 22, US data is state based, not zipcode
                # based
                numCases = int(fields[3])
            else:
                continue
        elif country == "Australia":
            # for australia, the individual territory are reported,
            # but no ZIP codes...
            if fields[3] == country and fields[0] == "":
                numCases = int(fields[7])
            else:
                continue
        elif fields[1] == country and (fields[0] == "" or fields[0] == country):
            # the format of the data changed at some point in
            # march. we can also make use the old format...
            numCases = int(fields[3])
        else:
            # line not applicable
            continue

        dt = fileNameToDateTime(file)

        if len(timeList) == 0 or timeList[-1] != dt:
            timeList.append(dt)
            totalCases.append(0)

        totalCases[-1] += numCases

# compute the number of daily new cases based on the total cases
for i, numCases in enumerate(totalCases):
    if i > 1:
        # some countries like Spain report a negative number of
        # new cases on some days, probably due to discovering
        # errors in data collection (e.g., cases counted multiple
        # times, etc.). while this is in general not a felony, it
        # spoils our curves too much, so we don't allow negative
        # new case numbers...
        deltaCases.append(max(0, numCases - totalCases[i - 1]))
    else:
        deltaCases.append(numCases)

deltaCasesSmoothend = boxFilter(deltaCases, n=7)
totalCasesSmoothend = boxFilter(totalCases, n=7)

# compute the attributable weight based on the filtered case deltas
attributableWeight = [0.0]*len(timeList)
for i in range(0, len(timeList)):
    # the new cases seen at day i are the ones which we need to
    # distribute amongst day i's neighbors using the weightList array
    for j, w in enumerate(weightsList):
        dayIdx = i + weightsOffset + j
        if dayIdx < 0:
            continue
        elif dayIdx + 1 > len(timeList):
            continue

        attributableWeight[dayIdx] += w * deltaCases[i]

# the estimated R factor of a given day simply is the ratio between
# number of observed cases and the attributable weight of that day.
estimatedR = []
for i, n in enumerate(deltaCases):
    R = 3.0
    if totalCasesSmoothend[i] >= 100 and attributableWeight[i] > 1e-10:
        R = n/attributableWeight[i]

    estimatedR.append(R)

# smoothen the R value, the inputs are generally much too noisy to be used directly
estimatedRSmothened = boxFilter(estimatedR, 14)

# print the results
print('Date "Total Cases" "New Cases" "Smoothened Total Cases" "Smoothened New Cases" "R Estimate" "Smoothened R Estimate"')
for i in range(0, len(timeList)):
    print("{} {} {} {} {} {} {}"
          .format(timeList[i].strftime("%Y-%m-%d"),
                  totalCases[i],
                  deltaCases[i],
                  totalCasesSmoothend[i],
                  deltaCasesSmoothend[i],
                  estimatedR[i],
                  estimatedRSmothened[i]))
