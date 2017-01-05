#!/usr/bin/env python3

# The MIT License (MIT)
# 
# Copyright (c) 2016, Sven Seeberg-Elverfeldt <sseebergelverfeldt@suse.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import multiprocessing, threading, queue, os, sys, json, string, hashlib, shutil, zipfile

from scipy.misc import imsave, imread
import numpy as np
from PyQt4 import QtGui, QtCore

from modules.qtcompare import qtImageCompare, toQImage
from modules.renderers import renderHtml, renderPdf
from modules.helpers import readFile, writeFile, modeToName
from modules.daps import daps


class myWorkThread (QtCore.QThread):
# worker threads which compile the DC files and compare the results
	def __init__(self,threadID, name, counter):
		QtCore.QThread.__init__(self)
		self.threadID = threadID
		self.name = name
		self.counter = counter
		
	def __del__(self):
		self.wait()

	def run(self):
		# we want the threads to keep running until the queue of test cases is empty
		while(True):
			testcase = ""
			foldersLock.acquire()
			if(folders.empty() == False):
				testcase = folders.get()
			foldersLock.release()
			# finish the thread if queue is empty
			if(testcase == ""):
				break
			outputTerminal(self.name+" now working on "+testcase)
			
			cleanDirectories(testcaseSubfolders = ['build'], rmConfigs=False, testcase=testcase)
			# compile DC files
			daps(testcase,cfg.dapsParam,cfg.filetypes)

			# render results to images
			runRenderers(testcase)
					
			if(cfg.mode == 2):
				runTests(testcase)
		outputTerminal(self.name+" finished")

#find the PDF files in build folder and convert to png
def preparePdf(testcase):
	folderName = testcase+modeToName(cfg.mode)+"/"+registerHash({'Type': 'pdf'})
	if not os.path.exists(folderName):
		os.makedirs(folderName)
	myRenderPdf = renderPdf(testcase+"build/*/*.pdf",100,folderName)

#find HTML files in build folder and convert to png
def prepareHtml(testcase):
	for build in os.listdir(testcase+"build"):
		if not build.startswith("."):
			for htmlBuild in os.listdir(testcase+"build/"+build+"/html/"):
				for htmlFile in os.listdir(testcase+"build/"+build+"/html/"+htmlBuild):
					for width in cfg.htmlWidth:
						folderName = testcase+modeToName(cfg.mode)+"/"+registerHash({'Type': 'html', 'Width': str(width)})+"/"
						if not os.path.exists(folderName):
							os.makedirs(folderName)
						if not os.path.islink(testcase+"build/"+build+"/html/"+htmlBuild+"/"+htmlFile):
							myRenderHtml = renderHtml(testcase+"build/"+build+"/html/"+htmlBuild+"/"+htmlFile,width,folderName)

#find Single HTML files in build folder and convert to png
def prepareSingleHtml(testcase):
	for build in os.listdir(testcase+"build"):
		if not build.startswith("."):
			for htmlBuild in os.listdir(testcase+"build/"+build+"/single-html/"):
				for htmlFile in os.listdir(testcase+"build/"+build+"/single-html/"+htmlBuild):
					for width in cfg.htmlWidth:
						folderName = testcase+modeToName(cfg.mode)+"/"+registerHash({'Type': 'single-html', 'Width': str(width)})+"/"
						if not os.path.exists(folderName):
							os.makedirs(folderName)
						if not os.path.islink(testcase+"build/"+build+"/single-html/"+htmlBuild+"/"+htmlFile):
							myRenderHtml = renderHtml(testcase+"build/"+build+"/single-html/"+htmlBuild+"/"+htmlFile,width,folderName)

#find EPUB files in build folder and convert to png
def prepareEpub(testcase):
	for build in os.listdir(testcase+"build"):
		if not build.startswith("."):
			for epub in os.listdir(testcase+"build/"+build+"/"):
				if epub.endswith(".epub"):
					os.makedirs(testcase+"build/"+build+"/"+epub[0:-5]+"/")
					zip_ref = zipfile.ZipFile(testcase+"build/"+build+"/"+epub, 'r')
					zip_ref.extractall(testcase+"build/"+build+"/"+epub[0:-5]+"/")
					zip_ref.close()
					for htmlFile in os.listdir(testcase+"build/"+build+"/"+epub[0:-5]+"/OEBPS/"):
						for width in cfg.htmlWidth:
							folderName = testcase+modeToName(cfg.mode)+"/"+registerHash({'Type': 'epub', 'Width': str(width)})+"/"
							if not os.path.exists(folderName):
								os.makedirs(folderName)
							if not os.path.islink(testcase+"build/"+build+"/"+epub[0:-5]+"/OEBPS/"+htmlFile):
								myRenderHtml = renderHtml(testcase+"build/"+build+"/"+epub[0:-5]+"/OEBPS/"+htmlFile,width,folderName)
# prepare for file types and then call the appropriate rendering modules
def runRenderers(testcase):
	for filetype in cfg.filetypes:
		if filetype == 'pdf':
			preparePdf(testcase)
		elif filetype == 'html' and cfg.noGui == False:
			prepareHtml(testcase)
		elif filetype == 'single-html' and cfg.noGui == False:
			prepareSingleHtml(testcase)
		elif filetype == 'epub' and cfg.noGui == False:
			prepareEpub(testcase)

def registerHash(params):
	# create md5sum of hash
	hashstring = json.dumps(params, sort_keys=True)
	md5 = hashlib.md5(hashstring.encode('utf-8'))
	# add md5sum and string to config and save to file in the end
	dataCollectionLock.acquire()
	dataCollection.depHashes[md5.hexdigest()] = params
	dataCollectionLock.release()
	return md5.hexdigest()

def listFiles(folder):
	result = []
	for item in os.listdir(folder):
		if os.path.isfile(folder+item):
			result.append(item)
	return result

# diff images of reference and compare run and save result
def runTests(testcase):
	for md5, description in dataCollection.depHashes.items():
		referencePath = testcase+"dapscompare-reference/"+md5+"/"
		comparisonPath = testcase+"dapscompare-comparison/"+md5+"/"
		numRefImgs = len(listFiles(referencePath))
		numComImgs = len(listFiles(comparisonPath))
		if (numRefImgs - numComImgs) != 0 and numRefImgs != 0:
			dataCollectionLock.acquire()
			dataCollection.diffNumPages.append([referencePath, numRefImgs, numComImgs])
			dataCollectionLock.release()
			print("Differing number of result images from "+referencePath)
			continue
		cleanDirectories(testcaseSubfolders = ['dapscompare-comparison','dapscompare-result'], rmConfigs=False, keepDirs=True, testcase=testcase)
		if not os.path.exists(referencePath):
			print("No reference images for "+dataCollection.depHashes[md5])
			continue
		diffFolder = testcase+"dapscompare-result/"+md5+"/"
		if not os.path.exists(diffFolder):
			os.makedirs(diffFolder)

		for filename in os.listdir(referencePath):
			imgRef = imread(referencePath+filename)
			imgComp = imread(comparisonPath+filename)
			try:
				imgDiff = imgRef - imgComp
				if np.count_nonzero(imgDiff) > 0:
					imsave(diffFolder+filename,imgDiff)
					outputTerminal("Image "+comparisonPath+filename+" has changed.")
					dataCollectionLock.acquire()
					dataCollection.imgDiffs.append([referencePath+filename, comparisonPath+filename, diffFolder+filename])
					dataCollectionLock.release()
			except:
				dataCollectionLock.acquire()
				dataCollection.diffNumPages.append([referencePath, numRefImgs, numComImgs])
				dataCollectionLock.release()
def outputTerminal(text):
	global outputLock
	outputLock.acquire()
	print (text)
	outputLock.release()      

class MyConfig:
	def __init__(self):

		self.stdValues()
		
		self.cmdParams()

		if self.loadConfigBool == True:
			self.loadConfig()

	def cmdParams(self):
		# first read CLI parameters
		for parameter in sys.argv:
			if parameter == "compare":
				self.mode = 2
			elif parameter == "reference":
				self.mode = 1
			elif parameter == "view":
				self.mode = 3
			elif parameter == "clean":
				self.mode = 4
			elif parameter == "--help":
				f = open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'README'), 'r')
				print(f.read())
				f.close()
				sys.exit()
			elif parameter == "--no-gui":
				self.noGui = True
			elif parameter.startswith("--daps="):
				self.dapsParam = parameter[7:]
			elif parameter.startswith("--testcases="):
				self.directory = parameter[12:]
			elif parameter == "--no-pdf":
				self.filetypes.remove('pdf')
			elif parameter == "--no-html":
				self.filetypes.remove('html')
			elif parameter == "--no-shtml":
				self.filetypes.remove('single-html')
			elif parameter == "--no-epub":
				self.filetypes.remove('epub')
			elif parameter.startswith("--html-width="):
				self.htmlWidth = parameter[13:].split(",")
			elif parameter == "--load-config":
				self.loadConfigBool = True

	def stdValues(self):
		self.resDiffFile = "dapscompare-diff.json"
		self.resHashFile = "dapscompare-hash.json"

		# set standard values for all other needed parameters
		self.directory = os.getcwd()+"/"

		# 1 = build reference
		# 2 = build comparison and run tests (standard)
		# 3 = view results of last run
		# 4 = clean
		self.mode = 0

		# usually show GUI after comparison
		if "DISPLAY" in os.environ:
			self.noGui = False
		else:
			self.noGui = True

		if self.noGui == True:
			self.filetypes = ['pdf']
		else:
			self.filetypes = ['pdf','html','single-html','epub']

		self.htmlWidth = [1280]

		self.dapsParam = "--force"

		self.loadConfigBool = False

	def loadConfig(self):
		content = readFile(self.directory+"/"+self.resHashFile)
		if content:
			self.filetypes = []
			content = json.loads(content)
			for hashsum in content:
				if content[hashsum]['Type'] not in self.filetypes:
					self.filetypes.append(content[hashsum]['Type'])
				if content[hashsum]['Type'] == "html":
					if int(content[hashsum]['Width']) not in self.htmlWidth:
						self.htmlWidth.append(int(content[hashsum]['Width']))

class DataCollector:
	def __init__(self):
		#if reference and comparison differ in number of pictures, store this here
		self.diffNumPages = []

		# compare or reference mode, new empty diff list
		self.imgDiffs = []
		# view mode, load existing diff list
		if cfg.mode == 3:
			imagesList = readFile(cfg.directory+cfg.resDiffFile)
			if imagesList == False:
				print("Nothing to do.")
				sys.exit()
			self.imgDiffs, self.diffNumPages = json.loads(imagesList)

		# hashes of dependencies like image width and filetype
		self.depHashes = {}
		fileContent = readFile(cfg.directory+cfg.resHashFile)		
		if (fileContent != False and len(fileContent)>2):
			self.depHashes = json.loads(fileContent)

def spawnWorkerThreads():
	# get number of available cpus. 
	# we want to compile as many test cases with daps at the same time 
	# as we can
	
	print("\n=== Parameters ===\n")
	
	cpus = multiprocessing.cpu_count()
	print("Number of CPUs: "+str(cpus))
	print("Working Directory: "+cfg.directory)
	print("Building: "+str(cfg.filetypes))
	global outputLock
	
	threads = []
	qWebWorkers = []
	outputLock = threading.Lock()
	
	queueTestcases()
	
	if folders.qsize() < cpus:
		cpus = folders.qsize()
	
	print ("\n=== Creating "+str(cpus)+" Threads ===\n")

	for threadX in range(0,cpus):
		thread = myWorkThread(threadX, "Thread-"+str(threadX), threadX)
		thread.start()
		threads.append(thread)

	# Wait for all threads to complete
	for t in threads:
		t.wait()
	print("All threads finished.")
	if cfg.mode == 2:
		writeFile(cfg.directory+cfg.resDiffFile,json.dumps([dataCollection.imgDiffs, dataCollection.diffNumPages]))
	writeFile(cfg.directory+cfg.resHashFile,json.dumps(dataCollection.depHashes))

def queueTestcases(silent=False):
	global folders,foldersLock
	folders = queue.Queue()
	foldersLock = threading.Lock()
	if not silent:
		print("\n=== Test Cases ===\n")
	n = 1
	foldersLock.acquire()
	for testcase in findTestcases():
		if not silent:
			print(str(n)+". "+testcase)
			n = n + 1
		folders.put(cfg.directory+testcase+"/")
	foldersLock.release()

def findTestcases():
	for testcase in os.listdir(cfg.directory):
		if(os.path.isdir(cfg.directory+"/"+testcase)):
			yield testcase

def cleanDirectories(testcaseSubfolders = ['dapscompare-reference','dapscompare-comparison','dapscompare-result','build'], rmConfigs=True, testcase=False, keepDirs = False):
	global foldersLock
	if testcase == False:
		testcases = findTestcases()
	else:
		testcases = [testcase]
		
	for testcase in testcases:
		for subfolder in testcaseSubfolders:
			try:
				if keepDirs:
					shutil.rmtree(testcase+"/"+subfolder+"/*")
				else:
					shutil.rmtree(testcase+"/"+subfolder)
			except:
				pass
	if rmConfigs:
		try:
			os.remove(cfg.directory+cfg.resHashFile)
		except:
			pass
		try:
			os.remove(cfg.directory+cfg.resDiffFile)	
		except:
			pass

def spawnGui():
	if cfg.noGui == False:
		print("Starting Qt GUI")
		if len(dataCollection.imgDiffs) > 0 or len(dataCollection.diffNumPages) > 0:
			ex = qtImageCompare(cfg,dataCollection)
			sys.exit(app.exec_())

def printResults():
	print("\n=== Changed Images ===\n")
	for item in dataCollection.imgDiffs:
		print(item[0])
	print("\n=== Differing Page Numbers ===\n")
	for item in dataCollection.diffNumPages:
		print(item[0])
	print()
	
def main():
	global app
	
	if "DISPLAY" in os.environ:
		app = QtGui.QApplication(sys.argv)
	else:
		app = QtCore.QCoreApplication(sys.argv)
		
	global cfg, dataCollection, dataCollectionLock
	cfg = MyConfig()
	dataCollection = DataCollector()
	dataCollectionLock = threading.Lock()
	
	if cfg.mode == 1 or cfg.mode == 2:
		spawnWorkerThreads()
	
	if (cfg.mode == 2 and cfg.noGui == False) or cfg.mode == 3:
		printResults()
		spawnGui()
		
	if cfg.mode == 4:
		cleanDirectories()
		
	if cfg.mode == 0:
		print("Nothing to do. Use --help.")

if __name__ == "__main__":
    main()
