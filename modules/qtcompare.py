from PyQt4 import QtGui, QtCore
import numpy as np
import sys
from scipy.misc import *

from PIL import ImageDraw, Image
import matplotlib.pyplot as plt
from scipy.cluster.vq import kmeans2, whiten, kmeans

gray_color_table = [QtGui.qRgb(i, i, i) for i in range(256)]

def toQImage(im, copy=False):
    if im is None:
        return QtGui.QImage()

    if im.dtype == np.uint8:
        if len(im.shape) == 2:
            qim = QtGui.QImage(im.data, im.shape[1], im.shape[0], im.strides[0], QtGui.QImage.Format_Indexed8)
            qim.setColorTable(gray_color_table)
            return qim.copy() if copy else qim

        elif len(im.shape) == 3:
            if im.shape[2] == 3:
                qim = QtGui.QImage(im.data, im.shape[1], im.shape[0], im.strides[0], QtGui.QImage.Format_RGB888);
                return qim.copy() if copy else qim
            elif im.shape[2] == 4:
                qim = QtGui.QImage(im.data, im.shape[1], im.shape[0], im.strides[0], QtGui.QImage.Format_ARGB32);
                return qim.copy() if copy else qim

    raise NotImplementedException

class qtImageCompare(QtGui.QMainWindow):
	# list images format list of triple reference image path, comparison image path, difference map image path 
	# [['reference path', 'comparison path', 'diffmap path'], ['reference path', 'comparison path', 'diffmap path'], [...] ...]
	def __init__(self,imagesList):
		super(qtImageCompare, self).__init__()
		self.initUI(imagesList)
        
	def initUI(self,imagesList):
		self.imagesList = imagesList
		self.imagePos = 0
		self.screenShape = QtGui.QDesktopWidget().screenGeometry()
		#self.resize(self.screenShape.width(), self.screenShape.height())
		self.resize(800,600)

		# Left image (reference)
		self.leftImage = QtGui.QLabel(self)
		self.leftImage.installEventFilter(self)
		self.leftImage.setAlignment(QtCore.Qt.AlignCenter)
		
		# Right image (comparison)
		self.rightImage = QtGui.QLabel(self)
		self.rightImage.installEventFilter(self)
		self.rightImage.setAlignment(QtCore.Qt.AlignCenter)
		
		# Next button
		self.btnNext = QtGui.QPushButton('Next', self)
		self.btnNext.clicked.connect(self.nextImage)
		
		# Previous button
		self.btnPrev = QtGui.QPushButton('Previous', self)
		self.btnPrev.clicked.connect(self.prevImage)
		
		# load initial images
		self.loadImage(imagesList[self.imagePos])
		
		self.show()
	
	@QtCore.pyqtSlot()
	def nextImage(self):
		if self.imagePos == len(self.imagesList) - 1:
			self.imagePos = 0
		else:
			self.imagePos = self.imagePos + 1
		self.loadImage(self.imagesList[self.imagePos])
	
	@QtCore.pyqtSlot()
	def prevImage(self):
		if self.imagePos == 0:
			self.imagePos = len(self.imagesList) - 1
		else:
			self.imagePos = self.imagePos - 1
		self.loadImage(self.imagesList[self.imagePos])
		
	def loadImageOld(self,path):
		self.pixmapLeft = QtGui.QPixmap(path[0])
		self.pixmapRight = QtGui.QPixmap(path[1])

		self.leftImage.setPixmap(self.pixmapLeft)
		self.rightImage.setPixmap(self.pixmapRight)
		
		self.calcPositions()

		self.rightImage.setPixmap(self.pixmapRight.scaled(
			self.rightImage.width(), self.rightImage.height(),
			QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
		self.leftImage.setPixmap(self.pixmapLeft.scaled(
			self.leftImage.width(), self.leftImage.height(),
			QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))

	def loadImage(self,path):
		# read all images
		referenceImage = imread(path[0])
		comparisonImage = imread(path[1])
		
		# flatten the diff map to reduce matrix complexity
		diffImage = imread(path[2],flatten=True)
		
		# get all coordinates that are not zero
		nonzeroCoords = np.nonzero(diffImage)
		
		# transform to 2 component vectors
		nonzeroCoords = np.column_stack((nonzeroCoords[0],nonzeroCoords[1]))
		
		# create image which can be used for drawing
		i = Image.fromarray(comparisonImage)
		draw = ImageDraw.Draw(i)
		
		# use k-means for the first iteration
		result = kmeans(nonzeroCoords.astype(float),1)
		n = 0
		
		# iterate k-means until the distortion is lower than 50
		while(result[1] > 15):
			n = n + 1
			result = kmeans(nonzeroCoords.astype(float),n)
		
		# draw boxes around all pixel groups
		for x, y in result[0]:
			x = x.astype(np.int64)
			y = y.astype(np.int64)
			coords = (y-25, x-25, y+25, x+25)
			draw.rectangle((coords), fill=None, outline="red")
		
		comparisonImage = np.asarray(i)
		
		self.pixmapLeft = QtGui.QPixmap.fromImage(toQImage(referenceImage))
		self.pixmapRight = QtGui.QPixmap.fromImage(toQImage(comparisonImage))

		self.leftImage.setPixmap(self.pixmapLeft)
		self.rightImage.setPixmap(self.pixmapRight)
		
		self.calcPositions()

		self.rightImage.setPixmap(self.pixmapRight.scaled(
			self.rightImage.width(), self.rightImage.height(),
			QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
		self.leftImage.setPixmap(self.pixmapLeft.scaled(
			self.leftImage.width(), self.leftImage.height(),
			QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
			
		
	def calcPositions(self):
		width = self.width()
		height = self.height()
		self.leftImage.move(0,0)
		self.leftImage.resize(width/2,height-70)
		self.rightImage.move(int(width/2)+1,0)
		self.rightImage.resize(width/2,height-70)
		self.btnNext.move(width - 120, height - 50)
		self.btnPrev.move(width - 240, height - 50)
		
	def resizeEvent(self,resizeEvent):
		self.calcPositions()
		
	def eventFilter(self, widget, event):
		if (event.type() == QtCore.QEvent.Resize and widget is self.leftImage):
			self.leftImage.setPixmap(self.pixmapLeft.scaled(
				self.leftImage.width(), self.leftImage.height(),
				QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
		if (event.type() == QtCore.QEvent.Resize and widget is self.rightImage):
			self.rightImage.setPixmap(self.pixmapRight.scaled(
				self.rightImage.width(), self.rightImage.height(),
				QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation))
		return QtGui.QMainWindow.eventFilter(self, widget, event)
		
#def main():
#	app = QtGui.QApplication(sys.argv)
#	ex = qtImageCompare([['../testcases/hitchhiker/dapscompare-reference/page-1.png','../testcases/hitchhiker/dapscompare-comparison/page-1.png','../testcases/hitchhiker/dapscompare-result/page-1.png'],
#						['../testcases/hitchhiker/dapscompare-reference/page-4.png','../testcases/hitchhiker/dapscompare-comparison/page-4.png','../testcases/hitchhiker/dapscompare-result/page-4.png'],
#						['../testcases/hitchhiker/dapscompare-reference/page-38.png','../testcases/hitchhiker/dapscompare-comparison/page-38.png','../testcases/hitchhiker/dapscompare-result/page-38.png'],
#						['../testcases/hitchhiker/dapscompare-reference/page-40.png','../testcases/hitchhiker/dapscompare-comparison/page-40.png','../testcases/hitchhiker/dapscompare-result/page-40.png']])
#	sys.exit(app.exec_())

#if __name__ == '__main__':
#	main()