# -------------------------------------------------------------------------------
# Name:        Download 3DEP data by county from a list
# Purpose:
#
# Author:      Bill Beaver
#
# Created:     01/22/2025
# Modified:    09/26/2025
# Copyright:   (c) bbeaver 2026
# Licence:     Open SOurce
# -------------------------------------------------------------------------------

import os
import datetime
import shutil

from urllib.parse import urlparse
import urllib.request, urllib.error
import shutil
import zipfile

def prepare():
    # base address
    sourceData = "https://gis1.oit.ohio.gov/ZIPARCHIVES_III/ELEVATION/3DEP/DEM/" # 1.25 foot DEM

    temp_base = r"" # Path to a temporary folder
    target_base = r"" # Path to a target folder
    destination = "" # Create a folder by this name in the target folder and name the csv file this name also

    params = dict(
        newTileDirectory=os.path.join(target_base,destination),

        # text file with list of tiles
        listExt=".csv",
        tileExt=".tif",

        sourceDataUrl=sourceData,
        numberFailed=0,
        tempFolder=temp_base,
        zipExt=".zip",
    )

    setup(params)

    unZipDEM(params)

    print(f'{params["numberFailed"]} uploads failed.')


def uploadBinaryFile(params, url):
    a = urlparse(url)

    destination = os.path.join(params["tempFolder"], os.path.basename(a.path))

    print(destination)

    try:
        with urllib.request.urlopen(url) as response, open(destination, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
    except (Exception,):
        print(f"URL : {url} failed!")
        params["numberFailed"] += 1


def setup(params):

    newTileDirectory = os.listdir(params["newTileDirectory"])
    listFile = None
    currentDEM = []

    for newFile in newTileDirectory:
        # get text file data list directory
        if newFile.endswith(params["listExt"]):
            listFile = os.path.join(params["newTileDirectory"], newFile)

        # current tiles
        elif newFile.endswith(params["tileExt"]):
            currentDEM.append(newFile)

        # error
        else:
            print(f"Problem with {newFile}")

    # get full data list
    with open(listFile, 'r') as file:

        skip = False
        for urlNum in file:
            # skip first line
            if skip:
                # split name and county
                rawName = urlNum.rstrip()
                rawsplit = rawName.split(",")
                base = rawsplit[0]
                testFile = base+params["tileExt"]
                county = rawsplit[1]

                # check to see if already downloaded
                if testFile not in currentDEM:
                    DEMfile = base+params["zipExt"]

                    url = urllib.parse.urljoin(params["sourceDataUrl"], county)+"/"
                    url = urllib.parse.urljoin(url, DEMfile)

                    print(url)
                    uploadBinaryFile(params, url)
            else:
                skip = True
                print(urlNum)

def unZipDEM(params):

    dir_name = params["tempFolder"]
    extension = params["zipExt"]
    target_name = params["newTileDirectory"]

    os.chdir(dir_name)  # change directory from working dir to dir with files

    for item in os.listdir(dir_name):  # loop through items in dir
        if item.endswith(extension):  # check for ".zip" extension
            try:
                file_name = os.path.abspath(item)  # get full path of files
                zip_ref = zipfile.ZipFile(file_name)  # create zipfile object
                zip_ref.extractall(target_name)  # extract file to dir
                zip_ref.close()  # close file
                os.remove(file_name)  # delete zipped file
            except (Exception,):
                print(f"File : {file_name} failed!")


def runDownloadFromList():
    prepare()


runDownloadFromList()
