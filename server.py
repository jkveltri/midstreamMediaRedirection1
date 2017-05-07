import os
import sys
import re
import datetime
from random import randint
try:
  from SimpleHTTPServer import SimpleHTTPRequestHandler as Handler
  from SocketServer import TCPServer as Server
  from SocketServer import ThreadingMixIn
except ImportError:
  from http.server import SimpleHTTPRequestHandler as Handler
  from http.server import HTTPServer as Server
  from socketserver import ThreadingMixIn


class ThreadingServer(ThreadingMixIn, Server):
    pass

class StateTracker(object):

    def __init__(self, logPath):
      self.stateTable = {}
      self.logPath = os.path.abspath(logPath)
      log = open(self.logPath, 'w')
      log.write("loadId,resReqNum,returnCode,url,date,time,dest_host,client_ip,client_port\n")
      log.close()

    def addRequestHistoryEvent(self, loadId, return_code, url, dest_host, client_addr):
      resReqNum = self.numRequestsForUrl(loadId, url)+1
      timestamp = datetime.datetime.now()
      stateEntry = self.stateTable.get(loadId)
      if not stateEntry:
        stateEntry = {}

      historyEntry = stateEntry.get(url)
      if not historyEntry:
        historyEntry = []

      historyEntry.append({'return_code':return_code, 'timestamp':timestamp, 'dest_host':dest_host, 'client_addr':client_addr})

      stateEntry[url] = historyEntry
      self.stateTable[loadId] = stateEntry

      log = open(self.logPath, 'a+')
      log.write("%s,%d,%d,%s,%s,%s,%s,%s,%d\n" % (loadId,resReqNum,return_code,url,timestamp.date(),timestamp.time(),dest_host,client_addr[0],client_addr[1]))
      log.close()

    def numRequestsForUrl(self, loadId, url):
      stateEntry = self.stateTable.get(loadId)
      if not stateEntry:
        return 0
      historyEntry = stateEntry.get(url)
      if not historyEntry:
        return 0
      return sum(1 if request['return_code'] == 200 else 0 for request in historyEntry)
      counter = 0
      

class CustomHandler(Handler):
    protocol_version = 'HTTP/1.0'

    # Initialize the state tracker
    #logFile = 'static/logs/log_' + datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S') + '.csv'
    logFile = 'static/logs/log.csv'
    stateTracker = StateTracker(logFile)

    def __init__(self, req, client_addr, server):
        Handler.__init__(self, req, client_addr, server)

    def respond200(self, filePath, cookie=None):
        try:
          # Guess the MIME type of the requested file
          mime = self.guess_type(filePath)

          # Read the file
          file = open(filePath, 'rb')
          content = file.read()
          file.close()

          # Send response
          content_length = len(content)
          self.send_response(200)
          self.send_header('Content-Type', mime)
          self.send_header('Access-Control-Allow-Origin','https://mmr.mybluemix.net')
          self.send_header('Content-Length', str(content_length))
          self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
          self.end_headers()
          self.wfile.write(content)
          return 200
  
        except IOError:
          print(sys.exc_info()[0])
          return self.respond400(404)
        
    def respond303(self, location):
        self.send_response(303)
        self.send_header('Location', location)
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Content-Length', 0)
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        return 303

    def respond400(self, code=400):
        code = code if (code >= 400 and code <= 499) else 400
        self.send_response(code)
        self.send_header('Content-Length', 0)
        self.end_headers()
        return code

    def separateQueryString(self, url):
        if '?' not in url:
          return url, None
        
        filePath = None
        queryString = None  
        matches = re.search('(.+)\?(.+)', url)
        if matches:
          filePath = matches.group(1)
          queryString = matches.group(2)
        return filePath, queryString

    def extractQueryParamValue(self, queryString, paramName):
        value = None
        reString = '.*' + re.escape(str(paramName)) + '=(\w+)\,?.+'
        matches = re.search(reString, queryString)
        if matches:
          value = matches.group(1)
        return value

    def lookForLoadId(self):
        loadId = None
        self.path, queryString = self.separateQueryString(self.path)
        if(queryString):
          loadId = self.extractQueryParamValue(queryString, 'loadId')
        if 'Referer' in self.headers and not loadId:
          refererPath, refererQueryString = self.separateQueryString(self.headers['Referer'])
          if refererQueryString:
            loadId = self.extractQueryParamValue(refererQueryString, 'loadId')
        return loadId

    def parseHostHeader(self):
        subhost = None
        superhost = None
        hostMatches = re.search('(mmr[\d]*)?\.?(\w+\.\w+[\d\:]*)', self.headers['Host'])
        if hostMatches:
          subhost = hostMatches.group(1)
          superhost = hostMatches.group(2)
        if not subhost:
          subhost = ''
        return subhost,superhost

    def do_GET(self):
        # Look for a load id in the query string or referer
        loadId = self.lookForLoadId()

        # Use http in localhost test mode, https on server
        devMode = 'localdevexample' in self.headers['Host'] # Edit hosts file to route localdevexample.com to 127.0.0.1
        httpType = 'https' if not devMode else 'http'

        # Parse the Host header
        subhost, superhost = self.parseHostHeader()

        """print('--------------------')
        print(self.client_address)
        print(self.headers)
        print(self.path)
        print(queryString)
        print(loadId)  
        print('Subhost: ' + subhost)
        print('Superhost: ' + superhost)"""

        returnCode = None

        # Serve index file if nothing specific requested
        if(self.path == '/'):
          self.path += 'index.html'

        # Only the html, css, and js can be loaded without a loadId (no manifest or segments)
        loadIdNotRequiredExtensions = ['.html','.js','.css','.csv']
        for extension in loadIdNotRequiredExtensions:
          if(self.path[-1*len(extension):] == extension):

            # Assign a loadId by redirecting loads of the html pages
            if(self.path.endswith('.html') and not self.path.endswith('index.html') and not loadId):
              returnCode = self.respond303(self.path + '?loadId=' + str(randint(1,1000000000)))
              return

            # Otherwise serve the file
            returnCode = self.respond200(self.path[1:])
            return

        # All other files require a loadId
        if(not loadId):
          print('Request requires a loadId, but one was not supplied')
          returnCode = self.respond400(403)
          return

        # Determine the experiment type (vod, live, or domainName) associated with the request
        manifestTypes = ['vod','live','domainName']
        manifestType = None
        typeMatches = re.search('\/(\w+)\/[\w\/]+.\w+', self.path);
        if(typeMatches and typeMatches.group(1) in manifestTypes):
          manifestType = typeMatches.group(1)
        else:
          returnCode = self.respond400()
          return

        # For .ts files, determine the segment number being requested
        segPrefix = None
        segNum = None
        if(self.path[-3:] == '.ts'):
          segMatches = re.search('.+\/([a-z,A-Z,_,-]+)(\d+).ts', self.path)
          if(segMatches):
            segPrefix = segMatches.group(1)
            segNum = segMatches.group(2)
          else:
            returnCode = self.respond400()
            return

        # Handle live-style manifests redirects
        if(manifestType == 'live'):           
          if(self.path[-5:] == '.m3u8'):
            manifestRequestNum = CustomHandler.stateTracker.numRequestsForUrl(loadId, self.path)+1

            if not('mmr' + str(manifestRequestNum) == subhost):
              if(manifestRequestNum == 1 or 'mmr' + str(manifestRequestNum-1) == subhost):
                redirectAddr = httpType + '://mmr' + str(manifestRequestNum) + '.' + superhost + self.path            
                returnCode = self.respond303(redirectAddr)
              else:
                returnCode = self.respond400(404)

            else:
              newPath = '/' + manifestType + '/' + manifestType + str(manifestRequestNum) + '.m3u8'
              returnCode = self.respond200(newPath[1:])

          elif(self.path[-3:] == '.ts'):
            genericManifestPath = '/' + manifestType + '/' + manifestType + '.m3u8'
            manifestRequestNum = CustomHandler.stateTracker.numRequestsForUrl(loadId, genericManifestPath)
            currManifestPath = manifestType + '/' + manifestType + str(manifestRequestNum) + '.m3u8'
            manifestFile = open(currManifestPath, 'r')
            manifestContent = manifestFile.read()
            manifestFile.close()
            subhostNum = 0 if len('mmr') >= len(subhost) else int(subhost[len('mmr'):])
            print(subhostNum)
            if(self.path[len(manifestType)+2:] in manifestContent and subhostNum <= manifestRequestNum and subhostNum > 0):
              print('respond 200')
              returnCode = self.respond200(self.path[1:])
            else:
              print('respond 404')
              returnCode = self.respond400(404)
              

        # Handle VOD or domainName style domain-prefix segment redirects
        elif(manifestType == 'vod' or manifestType == 'domainName'): 
          if(self.path[-3:] == '.ts'):
            if not(subhost == 'mmr' + segNum):
              returnCode = self.respond303(httpType + '://mmr' + str(segNum) + '.' + superhost + self.path)
            else:
              returnCode = self.respond200(self.path[1:])

        # Serve the file normally
        if not returnCode:
          returnCode = self.respond200(self.path[1:])

        # Log the request
        CustomHandler.stateTracker.addRequestHistoryEvent(loadId, returnCode, self.path, self.headers['Host'], self.client_address)


# Read port selected by the cloud for our application
PORT = int(os.getenv('PORT', 8000))

# Change current directory to avoid exposure of control files
os.chdir('static')

httpd = ThreadingServer(("", PORT), CustomHandler)
httpd.timeout = 10 # Set HTTP Keep-Alive timeout
try:
  print("Start serving at port %i" % PORT)
  httpd.serve_forever()
except KeyboardInterrupt:
  pass
httpd.server_close()

