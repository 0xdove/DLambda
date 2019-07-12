from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, JsonResponse, HttpResponseRedirect
# Create your views here.

import json
import boto3
import time
# from trp import Document

from django.views.decorators.csrf import csrf_exempt
from requests import Session
from zeep import Client
from requests.auth import HTTPBasicAuth
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
import urllib
import os

import datetime

class BoundingBox:
    def __init__(self, width, height, left, top):
        self._width = width
        self._height = height
        self._left = left
        self._top = top

    def __str__(self):
        return "width: {}, height: {}, left: {}, top: {}".format(self._width, self._height, self._left, self._top)

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def left(self):
        return self._left

    @property
    def top(self):
        return self._top

class Polygon:
    def __init__(self, x, y):
        self._x = x
        self._y = y

    def __str__(self):
        return "x: {}, y: {}".format(self._x, self._y)

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

class Geometry:
    def __init__(self, geometry):
        boundingBox = geometry["BoundingBox"]
        polygon = geometry["Polygon"]
        bb = BoundingBox(boundingBox["Width"], boundingBox["Height"], boundingBox["Left"], boundingBox["Top"])
        pgs = []
        for pg in polygon:
            pgs.append(Polygon(pg["X"], pg["Y"]))

        self._boundingBox = bb
        self._polygon = pgs

    def __str__(self):
        s = "BoundingBox: {}\n".format(str(self._boundingBox))
        return s

    @property
    def boundingBox(self):
        return self._boundingBox

    @property
    def polygon(self):
        return self._polygon

class Word:
    def __init__(self, block, blockMap):
        self._block = block
        self._confidence = block['Confidence']
        self._geometry = Geometry(block['Geometry'])
        self._id = block['Id']
        self._text = ""
        if(block['Text']):
            self._text = block['Text']

    def __str__(self):
        return self._text

    @property
    def confidence(self):
        return self._confidence

    @property
    def geometry(self):
        return self._geometry

    @property
    def id(self):
        return self._id

    @property
    def text(self):
        return self._text

    @property
    def block(self):
        return self._block

class Line:
    def __init__(self, block, blockMap):

        self._block = block
        self._confidence = block['Confidence']
        self._geometry = Geometry(block['Geometry'])
        self._id = block['Id']

        self._text = ""
        if(block['Text']):
            self._text = block['Text']

        self._words = []
        if('Relationships' in block and block['Relationships']):
            for rs in block['Relationships']:
                if(rs['Type'] == 'CHILD'):
                    for cid in rs['Ids']:
                        if(blockMap[cid]["BlockType"] == "WORD"):
                            self._words.append(Word(blockMap[cid], blockMap))
    def __str__(self):
        s = "Line\n==========\n"
        s = s + self._text + "\n"
        s = s + "Words\n----------\n"
        for word in self._words:
            s = s + "[{}]".format(str(word))
        return s

    @property
    def confidence(self):
        return self._confidence

    @property
    def geometry(self):
        return self._geometry

    @property
    def id(self):
        return self._id

    @property
    def words(self):
        return self._words

    @property
    def text(self):
        return self._text

    @property
    def block(self):
        return self._block

class SelectionElement:
    def __init__(self, block, blockMap):
        self._confidence = block['Confidence']
        self._geometry = Geometry(block['Geometry'])
        self._id = block['Id']
        self._selectionStatus = block['SelectionStatus']

    @property
    def confidence(self):
        return self._confidence

    @property
    def geometry(self):
        return self._geometry

    @property
    def id(self):
        return self._id

    @property
    def selectionStatus(self):
        return self._selectionStatus

class FieldKey:
    def __init__(self, block, children, blockMap):
        self._block = block
        self._confidence = block['Confidence']
        self._geometry = Geometry(block['Geometry'])
        self._id = block['Id']
        self._text = ""
        self._content = []

        t = []

        for eid in children:
            wb = blockMap[eid]
            if(wb['BlockType'] == "WORD"):
                w = Word(wb, blockMap)
                self._content.append(w)
                t.append(w.text)

        if(t):
            self._text = ' '.join(t)

    def __str__(self):
        return self._text

    @property
    def confidence(self):
        return self._confidence

    @property
    def geometry(self):
        return self._geometry

    @property
    def id(self):
        return self._id

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        return self._text

    @property
    def block(self):
        return self._block

class FieldValue:
    def __init__(self, block, children, blockMap):
        self._block = block
        self._confidence = block['Confidence']
        self._geometry = Geometry(block['Geometry'])
        self._id = block['Id']
        self._text = ""
        self._content = []

        t = []

        for eid in children:
            wb = blockMap[eid]
            if(wb['BlockType'] == "WORD"):
                w = Word(wb, blockMap)
                self._content.append(w)
                t.append(w.text)
            elif(wb['BlockType'] == "SELECTION_ELEMENT"):
                se = SelectionElement(wb, blockMap)
                self._content.append(se)
                self._text = se.selectionStatus

        if(t):
            self._text = ' '.join(t)

    def __str__(self):
        return self._text

    @property
    def confidence(self):
        return self._confidence

    @property
    def geometry(self):
        return self._geometry

    @property
    def id(self):
        return self._id

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        return self._text
    
    @property
    def block(self):
        return self._block

class Field:
    def __init__(self, block, blockMap):
        self._key = None
        self._value = None

        for item in block['Relationships']:
            if(item["Type"] == "CHILD"):
                self._key = FieldKey(block, item['Ids'], blockMap)
            elif(item["Type"] == "VALUE"):
                for eid in item['Ids']:
                    vkvs = blockMap[eid]
                    if 'VALUE' in vkvs['EntityTypes']:
                        if('Relationships' in vkvs):
                            for vitem in vkvs['Relationships']:
                                if(vitem["Type"] == "CHILD"):
                                    self._value = FieldValue(vkvs, vitem['Ids'], blockMap)
    def __str__(self):
        s = "\nField\n==========\n"
        k = ""
        v = ""
        if(self._key):
            k = str(self._key)
        if(self._value):
            v = str(self._value)
        s = s + "Key: {}\nValue: {}".format(k, v)
        return s

    @property
    def key(self):
        return self._key

    @property
    def value(self):
        return self._value

class Form:
    def __init__(self):
        self._fields = []
        self._fieldsMap = {}

    def addField(self, field):
        self._fields.append(field)
        self._fieldsMap[field.key.text] = field

    def __str__(self):
        s = ""
        for field in self._fields:
            s = s + str(field) + "\n"
        return s

    @property
    def fields(self):
        return self._fields

    def getFieldByKey(self, key):
        field = None
        if(key in self._fieldsMap):
            field = self._fieldsMap[key]
        return field
    
    def searchFieldsByKey(self, key):
        searchKey = key.lower()
        results = []
        for field in self._fields:
            if(field.key and searchKey in field.key.text.lower()):
                results.append(field)
        return results

class Cell:

    def __init__(self, block, blockMap):
        self._block = block
        self._confidence = block['Confidence']
        self._rowIndex = block['RowIndex']
        self._columnIndex = block['ColumnIndex']
        self._rowSpan = block['RowSpan']
        self._columnSpan = block['ColumnSpan']
        self._geometry = Geometry(block['Geometry'])
        self._id = block['Id']
        self._content = []
        self._text = ""
        if('Relationships' in block and block['Relationships']):
            for rs in block['Relationships']:
                if(rs['Type'] == 'CHILD'):
                    for cid in rs['Ids']:
                        blockType = blockMap[cid]["BlockType"]
                        if(blockType == "WORD"):
                            w = Word(blockMap[cid], blockMap)
                            self._content.append(w)
                            self._text = self._text + w.text + ' '
                        elif(blockType == "SELECTION_ELEMENT"):
                            se = SelectionElement(blockMap[cid], blockMap)
                            self._content.append(se)
                            self._text = self._text + se.selectionStatus + ', '

    def __str__(self):
        return self._text

    @property
    def confidence(self):
        return self._confidence

    @property
    def rowIndex(self):
        return self._rowIndex

    @property
    def columnIndex(self):
        return self._columnIndex

    @property
    def rowSpan(self):
        return self._rowSpan

    @property
    def columnSpan(self):
        return self._columnSpan

    @property
    def geometry(self):
        return self._geometry

    @property
    def id(self):
        return self._id

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        return self._text

    @property
    def block(self):
        return self._block

class Row:
    def __init__(self):
        self._cells = []

    def __str__(self):
        s = ""
        for cell in self._cells:
            s = s + "[{}]".format(str(cell))
        return s

    @property
    def cells(self):
        return self._cells

class Table:

    def __init__(self, block, blockMap):

        self._block = block

        self._confidence = block['Confidence']
        self._geometry = Geometry(block['Geometry'])

        self._id = block['Id']
        self._rows = []

        ri = 1
        row = Row()
        cell = None
        if('Relationships' in block and block['Relationships']):
            for rs in block['Relationships']:
                if(rs['Type'] == 'CHILD'):
                    for cid in rs['Ids']:
                        cell = Cell(blockMap[cid], blockMap)
                        if(cell.rowIndex > ri):
                            self._rows.append(row)
                            row = Row()
                            ri = cell.rowIndex
                        row.cells.append(cell)
                    if(row and row.cells):
                        self._rows.append(row)

    def __str__(self):
        s = "Table\n==========\n"
        for row in self._rows:
            s = s + "Row\n==========\n"
            s = s + str(row) + "\n"
        return s

    @property
    def confidence(self):
        return self._confidence

    @property
    def geometry(self):
        return self._geometry

    @property
    def id(self):
        return self._id

    @property
    def rows(self):
        return self._rows

    @property
    def block(self):
        return self._block

class Page:

    def __init__(self, blocks, blockMap):
        self._blocks = blocks
        self._text = ""
        self._lines = []
        self._form = Form()
        self._tables = []
        self._content = []

        self._parse(blockMap)

    def __str__(self):
        s = "Page\n==========\n"
        for item in self._content:
            s = s + str(item) + "\n"
        return s

    def _parse(self, blockMap):
        for item in self._blocks:
            if item["BlockType"] == "PAGE":
                self._geometry = Geometry(item['Geometry'])
                self._id = item['Id']
            elif item["BlockType"] == "LINE":
                l = Line(item, blockMap)
                self._lines.append(l)
                self._content.append(l)
                self._text = self._text + l.text + '\n'
            elif item["BlockType"] == "TABLE":
                t = Table(item, blockMap)
                self._tables.append(t)
                self._content.append(t)
            elif item["BlockType"] == "KEY_VALUE_SET":
                if 'KEY' in item['EntityTypes']:
                    f = Field(item, blockMap)
                    if(f.key):
                        self._form.addField(f)
                        self._content.append(f)
                    else:
                        print("WARNING: Detected K/V where key does not have content. Excluding key from output.")
                        print(f)
                        print(item)

    def getLinesInReadingOrder(self):
        columns = []
        lines = []
        for item in self._lines:
                column_found=False
                for index, column in enumerate(columns):
                    bbox_left = item.geometry.boundingBox.left
                    bbox_right = item.geometry.boundingBox.left + item.geometry.boundingBox.width
                    bbox_centre = item.geometry.boundingBox.left + item.geometry.boundingBox.width/2
                    column_centre = column['left'] + column['right']/2
                    if (bbox_centre > column['left'] and bbox_centre < column['right']) or (column_centre > bbox_left and column_centre < bbox_right):
                        #Bbox appears inside the column
                        lines.append([index, item.text])
                        column_found=True
                        break
                if not column_found:
                    columns.append({'left':item.geometry.boundingBox.left, 'right':item.geometry.boundingBox.left + item.geometry.boundingBox.width})
                    lines.append([len(columns)-1, item.text])

        lines.sort(key=lambda x: x[0])
        return lines

    def getTextInReadingOrder(self):
        lines = self.getLinesInReadingOrder()
        text = ""
        for line in lines:
            text = text + line[1] + '\n'
        return text

    @property
    def blocks(self):
        return self._blocks

    @property
    def text(self):
        return self._text

    @property
    def lines(self):
        return self._lines

    @property
    def form(self):
        return self._form

    @property
    def tables(self):
        return self._tables

    @property
    def content(self):
        return self._content

    @property
    def geometry(self):
        return self._geometry

    @property
    def id(self):
        return self._id

class Document:

    def __init__(self, responsePages):

        if(not isinstance(responsePages, list)):
            rps = []
            rps.append(responsePages)
            responsePages = rps

        self._responsePages = responsePages
        self._pages = []

        self._parse()

    def __str__(self):
        s = "\nDocument\n==========\n"
        for p in self._pages:
            s = s + str(p) + "\n\n"
        return s

    def _parseDocumentPagesAndBlockMap(self):

        blockMap = {}

        documentPages = []
        documentPage = None
        for page in self._responsePages:
            for block in page['Blocks']:
                if('BlockType' in block and 'Id' in block):
                    blockMap[block['Id']] = block

                if(block['BlockType'] == 'PAGE'):
                    if(documentPage):
                        documentPages.append({"Blocks" : documentPage})
                    documentPage = []
                    documentPage.append(block)
                else:
                    documentPage.append(block)
        if(documentPage):
            documentPages.append({"Blocks" : documentPage})
        return documentPages, blockMap

    def _parse(self):

        self._responseDocumentPages, self._blockMap = self._parseDocumentPagesAndBlockMap()
        for documentPage in self._responseDocumentPages:
            page = Page(documentPage["Blocks"], self._blockMap)
            self._pages.append(page)

    @property
    def blocks(self):
        return self._responsePages

    @property
    def pageBlocks(self):
        return self._responseDocumentPages

    @property
    def pages(self):
        return self._pages

    def getBlockById(self, blockId):
        block = None
        if(self._blockMap and blockId in self._blockMap):
            block = self._blockMap[blockId]
        return block


def startJob(s3BucketName, objectName):
    
    response = None
    client = boto3.client('textract')
    response = client.start_document_analysis(
        DocumentLocation={
            'S3Object': {
                'Bucket': s3BucketName,
                'Name': objectName
            }
        },
        FeatureTypes=[
            'TABLES', 'FORMS'
        ])

    return response["JobId"]

def isJobComplete(jobId):
    # For production use cases, use SNS based notification
    # Details at: https://docs.aws.amazon.com/textract/latest/dg/api-async.html
    time.sleep(5)
    client = boto3.client('textract')
    response = client.get_document_analysis(JobId=jobId)
    status = response["JobStatus"]
    print("Job status: {}".format(status))

    while(status == "IN_PROGRESS"):
        time.sleep(5)
        response = client.get_document_analysis(JobId=jobId)
        status = response["JobStatus"]
        print("Job status: {}".format(status))

    return status


def getJobResults(jobId):

    pages = []

    client = boto3.client('textract')
    response = client.get_document_analysis(JobId=jobId)

    pages.append(response)
    print("Resultset page recieved: {}".format(len(pages)))
    nextToken = None
    if('NextToken' in response):
        nextToken = response['NextToken']

    while(nextToken):

        response = client.get_document_analysis(
            JobId=jobId, NextToken=nextToken)

        pages.append(response)
        print("Resultset page recieved: {}".format(len(pages)))
        nextToken = None
        if('NextToken' in response):
            nextToken = response['NextToken']

    return pages


def getTextConfidence(inputData, arrTextConf, arrOriginText):
    resultList = []
    for item in inputData:
        key_text = set(item).intersection(arrOriginText)
        if(key_text):
            key_text_str = key_text.pop()
            for i in range(len(arrTextConf)):
                subItem = arrTextConf[i]
                if subItem["key_name"].lower() == key_text_str:
                    resultList.append(
                        {"Name": subItem["key_name"], "Confidence": subItem["key_conf"]})
                    break
                elif i == len(arrTextConf)-1:
                    resultList.append(
                        {"Name": key_text_str, "Confidence": 0})
        else:
            resultList.append(
                {"Name": item[0], "Confidence": 0})
    return resultList

@csrf_exempt
def lambda_handler(request):
    if request.method == 'POST':
        print ("hello")
        # Document
        param = request.body
        paramObject = json.loads(param)

        documentName = paramObject['name']
        inputFormat = paramObject['inputFormat']

        s3BucketName = "textract-backup"

        jobId = startJob(s3BucketName, documentName)
        
        print("Started job with id: {}".format(jobId))

        if(isJobComplete(jobId)):
            response = getJobResults(jobId)

        arrOriginText = []
        arrTextConf = []
        for item in response[0]["Blocks"]:
            if item["BlockType"] == "LINE":
                arrOriginText.append(item["Text"].lower())
                for subItem in response[0]["Blocks"]:
                    if subItem["BlockType"] == "KEY_VALUE_SET" and subItem['EntityTypes'][0] == 'KEY':
                        if subItem["Relationships"][1] == item["Relationships"][0]:
                            arrTextConf.append(
                                {"key_name": item["Text"], "key_conf": subItem["Confidence"]})
                            break

        # arrOriginText = ['date shippped', 'origin', 'dest', 'airbill number', '12/07/2018', '12072018-1', 'jade logistics, inc.', 'invoice number', 'third party', '975772528', 'shipper reference', 'consignee reference', 'ref # 12072018-1', 'ref #', 'baldinger baking co. ltd', "son's bakery", '1256 phalen blvd.', '8 atlas court', 'st. paul mn 55106', 'brampton on l6', 'brad blair', '651-224-5761', 'darren sambucharan', '416-459-1603', 'pieces', 'description', 'weight', 'rate', 'chargeable lb', 'declared value', '13',
        #                  '3000 empty bun trays(doubles)', '13500', '$2,700.00', '13', 'iiiiiiiiiiiiiiiiiiiiiii totals iiiiiiiiiiiiiiiiiiiiiiii', '13500', '$2,700.00', '13500', 'type of service:', '2 day tl', 'special instructions', 'broker: ghy & crossing-windsor', "rier'fulger transport inc", 'dimensional measurement', 'pieces', 'length', 'width', 'height', 'cubic inches', '13', '40', '48', '48', '92160', 'description of charges', 'amount', 'dimensional', '555', 'cubic', 'feet', '53', 'cubic', 'weight', 'inches', '92160', 'jade logistics is a minnesota corp. fed id 41-2234546', 'bill to', 'all amounts shown are in u.s. dollars', 'baldinger bakery pkg', '1256 phalen bivd.', 'st. paul mn 55106', '$2,700.00', 'attn: james reyes', 'date invoiced: december 11, 2018', 'proof of delivery', 'rec', 'tariff regulations require payment by:', 'delivered', '12/09/2018', 'january 10, 2019', 'please remit to', 'jade logistics', 'if you have any questions regarding this inv oice,', 'please callor email jade at 651-405-3141 or', '1590 thomas center dr ste 100', 'accounting@shipjade.com thank you for your', 'eagan, mn 55122', 'assistance in this matter.']
        # arrTextConf = [{'key_name': 'DATE SHIPPPED', 'key_conf': 50.059391021728516}, {'key_name': 'ORIGIN', 'key_conf': 67.1324462890625}, {'key_name': 'DEST', 'key_conf': 64.25784301757812}, {'key_name': 'AIRBILL NUMBER', 'key_conf': 71.31368255615234}, {'key_name': 'Invoice Number', 'key_conf': 65.50056457519531}, {'key_name': "Son's Bakery", 'key_conf': 42.13179397583008}, {'key_name': '8 Atlas Court', 'key_conf': 42.602474212646484}, {'key_name': 'Brad Blair', 'key_conf': 55.96393966674805}, {
        #     'key_name': 'DARREN SAMBUCHARAN', 'key_conf': 47.307945251464844}, {'key_name': 'PIECES', 'key_conf': 59.2801399230957}, {'key_name': 'LENGTH', 'key_conf': 51.812042236328125}, {'key_name': 'WIDTH', 'key_conf': 39.425785064697266}, {'key_name': 'HEIGHT', 'key_conf': 38.66687774658203}, {'key_name': 'CUBIC INCHES', 'key_conf': 43.43712615966797}, {'key_name': '13', 'key_conf': 40.27323532104492}, {'key_name': 'Delivered', 'key_conf': 53.88093566894531}]

        ret_result_first = getTextConfidence(
            inputFormat["input_first"], arrTextConf, arrOriginText)
        ret_result_second = getTextConfidence(
            inputFormat["input_second"], arrTextConf, arrOriginText)
        # print(ret_result_first)
        # print(ret_result_second)

        doc = Document(response)

        for page in doc.pages:
            for i in range(len(ret_result_first)):
                item = ret_result_first[i]
                field = page.form.getFieldByKey(item["Name"])
                if(field):
                    ret_result_first[i] = {"Name": item["Name"],
                                        "Confidence": item["Confidence"], "Value": str(field.value)}
                else:
                    ret_result_first[i] = {"Name": item["Name"],
                                        "Confidence": item["Confidence"], "Value": ""}

        ordList = []
        ret_result_second_new = []
        for page in doc.pages:
            # Print tables
            for r, row in enumerate(page.tables[0].rows):
                if r == 0:
                    for i in range(len(ret_result_second)):
                        item = ret_result_second[i]

                        for i in range(len(row.cells)):
                            cell = row.cells[i]
                            if item["Name"].lower() == cell.text.strip().lower():
                                ordList.append(
                                    {"Name": cell.text.strip(), "Order": i, "Confidence": item["Confidence"]})
                                break
                            elif i == len(row.cells)-1:
                                ordList.append(
                                    {"Name": item["Name"], "Order": -1, "Confidence": item["Confidence"]})
                    print(ordList)
                    continue
                if row.cells[0].text.strip() == '':
                    break

                subTable = []
                for i in range(len(ordList)):
                    item = ordList[i]
                    if ordList[i]["Order"] < -1:
                        print('test')
                    subTable.append(
                        {
                            "Name": item["Name"], "Value":  str(row.cells[item["Order"]].text.strip()), "Confidence": row.cells[item["Order"]].confidence})

                ret_result_second_new.append(subTable)
        ret_result = {"output_first": ret_result_first,
                    "output_second": ret_result_second_new}
        return JsonResponse({
            'statusCode': 200,
            'body': ret_result
        })
