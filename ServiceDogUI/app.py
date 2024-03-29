# 2019-06-06
# ServiceDogUI (User Interface)
# Written by Grant, Veronique, Jonas, Alberto

import uuid
import os, sys, re, time
import boto
import requests, json
from flask import Flask, jsonify, render_template, redirect, request, url_for, make_response, session
import flask
from werkzeug import secure_filename
from PIL import Image, ImageOps
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from werkzeug import secure_filename
from pymongo import MongoClient
import pymongo
import qrcode

## Declare environment variables
ecs_access_key_id = os.environ['ECS_access_key']
ecs_secret_key = os.environ['ECS_secret']
## We can now extract "namespace" from the access key
namespace = ecs_access_key_id.split('@')[0]

session = boto.connect_s3(ecs_access_key_id, ecs_secret_key, host='object.ecstestdrive.com')

# Dog Photo bucket
bname = 'dogphotos'
b = session.get_bucket(bname)
print str(b)

# Document Admin bucket
docadmin_bname = 'docadmin'
docadmin_s3 = session.get_bucket(docadmin_bname)
print str(docadmin_s3)

app = Flask(__name__)
app.config['ALLOWED_EXTENSIONS'] = set(['jpg', 'jpeg', 'JPG', 'JPEG', 'pdf', 'PDF'])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']

global dogsname
dogsname = ''
global handlersname
handlersname = ''

## Identify where we're running
if 'VCAP_SERVICES' in os.environ:
    handler_api = os.environ['HANDLER_API']
    dog_api = os.environ['DOG_API']
    ui_url=os.environ['UI_URL']
    doco_api = os.environ['DOCO_API']

else:
    handler_api = "http://127.0.0.1:5010"
    dog_api = "http://127.0.0.1:5020"
    ui_url = "http://127.0.0.1:5030"
    doco_api = "http://127.0.0.1:5140"
    auth_api = "http://127.0.0.1:5050"    

my_uuid = str(uuid.uuid1())
username = ""
userstatus = "0"

@app.route('/')
def menu():

    current = int(time.time())-time.timezone
    global userstatus

    uuid = request.cookies.get('uuid')
    if uuid and not uuid == "0":
        userstatus = "1"
    else:
        userstatus = "0"

    resp = make_response(render_template('main_menu.html', userstatus=userstatus, uuid=uuid))
    return resp

### Basic login for demo purposes only, not intended to secure app access
@app.route('/loginform', methods=['GET','POST'])
def loginform():

    global uuid
    global username
    global userstatus

    uuid = request.cookies.get('uuid')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

    if not uuid:
        # No UUID, the user need to authenticate OR the user credentials were invalid
        print "uuid cookie was not present"

        if request.method == 'GET':
            # First time user accesses page. Show login form
            resp = make_response(render_template('loginform.html', login="loginform", status=""))

        else:
            userstatus  = "1"
            userrole    = "administrator"

            if userstatus == "1":
                # User login successful
                resp = make_response(render_template('logincomplete.html', uuid=my_uuid))
                resp.set_cookie('uuid',str(my_uuid), max_age=1800)

            elif userstatus == "0":
                # User has a failed login
                resp = make_response(render_template('loginform.html', login="loginform", status="Username or password was incorrect. Please try again."))
    else:
        resp = make_response(render_template('logincomplete.html', uuid=my_uuid))
        resp.set_cookie('uuid',str(my_uuid), max_age=1800)

    return resp

@app.route('/logout', methods=['GET','POST'])
def logout():
    global uuid

    uuid = request.cookies.get('uuid')

    if not uuid:
        print "User trying to log out but is not logged in."
        resp = make_response(render_template('logoutform.html', status="Session not active. No need to log out."))

    else:
        resp = make_response(render_template('logoutform.html', status="Your session has been closed."))
        resp.set_cookie('uuid',str(my_uuid), max_age=0)

    return resp

############################
# Admin Menu - All Options #
############################

@app.route('/admin')
def admin():
    resp = make_response(render_template('admin.html', userstatus=userstatus))
    return resp

###########################
# Document-related routes #
###########################

### Add document functions: GET and POST
@app.route('/addoc')
def addoc():
    # Render HTML page to request the new document's information
    # Expect: handler_id, dog_id, doco_type and document file
    resp = make_response(render_template('newdoc.html'))
    return resp

@app.route('/addocoprocess.html', methods=['POST'])
def addocoprocess():

    doc_details = request.form.to_dict()
    print ("doc_details:" ), doc_details

    # Call the docadmin service to insert new document record, expect 
    url = doco_api + "/api/v1.0/doco"
    api_resp = requests.post(url, json=doc_details)
    dict_resp = json.loads(api_resp.content)
    
    # The following line returns the instance's unique mongodb _id and stores in doco_id variable
    # doco_id is used as part of document name in S3 bucket
    doco_id = dict_resp["doco"]["id"]
    docname = doco_id + ".pdf"

    ## Now we can upload the photo with a name based on doco_id
    myfile = request.files['file']
    # First get the file name and see if it's secure
    if myfile and allowed_file(myfile.filename):
        upload_doc(myfile, docname)

    # This is how the document will be reached
    docuri = "http://" + namespace + ".public.ecstestdrive.com/" + docadmin_bname + "/" + docname
    namedata = {"name": docuri}
    doc_url = url + "/" + doco_id
    name_resp = requests.put(doc_url, json=namedata)

    # We now need to load the full document details in
    doc_response = requests.get(doc_url)
    alldoc_details = json.loads(doc_response.content)
    
    resp = make_response(render_template('docuploaded.html', doco_id=doco_id, doc_details=alldoc_details["doco"]))
    return resp

### Search for document
@app.route('/searchdoco')
def searchdoco():
    resp = make_response(render_template('searchdoco.html'))
    return resp
    
@app.route('/searchdocoresults', methods=['POST']) # displays result of search in searchdoco
def searchdocoresults():

    criteria = request.form['criteria']
    match = request.form['match'].lower()
    print "Searching for {} = {}".format(criteria.lower(), match.lower())

    payload = {criteria : match}
    print ("payload", payload)
    url = doco_api + "/api/v1.0/search"
    response = requests.put(url, json=payload)
    print ("response: ", response)
    dict_resp = json.loads(response.content)

    resp = make_response(render_template('searchdocoresults.html', results=dict_resp["documents"]))
    return resp

### View document details by providing its unique ID
@app.route('/viewdoco')
def viewdoco():

    global username
    userid = "admin"

    doco_id = request.args.get('doco_id')
    url = doco_api + "/api/v1.0/doco/" + doco_id
    
    response = requests.get(url)
    dict_resp = json.loads(response.content)

##    resp = make_response(render_template('viewhandler.html', handlerinfo=dict_resp["handler"], h_id=h_id))
    resp = make_response(render_template('viewdoco.html', doco_id=doco_id, doco_details=dict_resp["doco"]))
    return resp


### Edit document
@app.route('/editdoco')
def editdoco():
    doco_id = ""
    doco_id = request.args.get('doco_id')
    resp = make_response(render_template('editdoco.html', doco_id=doco_id))
    return resp

@app.route('/editdocoshowcurrent.html', methods=['GET','POST'])
def editdocoshowcurrent():

    if request.method == 'GET':
        doco_id = request.args.get('doco_id')

    if request.method == 'POST':
        doco_id = request.form['doco_id']

    ## Now we call the document microservice to read the document
    url = doco_api + "/api/v1.0/doco/" + doco_id
    api_resp = requests.get(url)
    dict_resp = json.loads(api_resp.content)
    # The response is formatted as { "doco" : {"doco_type":"vaccination", "handler_id":"h_id123"}, {},...}
    doco_to_edit = dict_resp["doco"]
    print doco_to_edit
    docfile = "http://" + namespace + ".public.ecstestdrive.com/" + docadmin_bname + "/" + doco_id + ".pdf"

    resp = make_response(render_template('currentdoco.html', doco_id=doco_id, doco_details=doco_to_edit, name=docfile))
    return resp

@app.route('/editdocoapplychanges.html', methods=['POST'])
def editdocoapplychanges():

    doco_details = request.form.to_dict()
    # print doco_details
    print("DOCUMENT DETAILS: %s" % doco_details)

    # Call the document microservice to insert it and get a dogid back
    doco_id = str(request.form['doco_id'])
    url = doco_api + "/api/v1.0/doco/" + doco_id
    api_resp = requests.put(url, json=doco_details)
    dict_resp = json.loads(api_resp.content)

    docfile = "http://" + namespace + ".public.ecstestdrive.com/" + docadmin_bname + "/" + doco_id + ".pdf"

    resp = make_response(render_template('docomodified.html', doco_id=doco_id, doco_details=dict_resp["doco"], name=docfile))
    return resp

######################
# Dog-related routes #
######################

### Menu of dog available actions
@app.route('/dogs')
def dogs():
    # global userstatus
    resp = make_response(render_template('dogs.html', userstatus=userstatus))
    return resp

@app.route('/searchdog') # search page which submits to viewdog
def searchdog():
    resp = make_response(render_template('searchdog.html', viewdog="viewdog"))
    return resp

@app.route('/searchdogresults', methods=['POST']) # displays result of dog ID search in searchdog
def searchdogresults():

    criteria = request.form['criteria']
    match = request.form['match'].lower()
    print "Searching for {} = {}".format(criteria.lower(), match.lower())
    # Convert True/False strings to boolean as required by API
    if criteria in ["vacc_status", "reg_status"] and match in ["true", "false"]:
        match = str2bool(match)
    if criteria == "handler_id" and match == "none":
        match = None
        print type(match)
    payload = {criteria : match}
    print payload
    url = dog_api + "/api/v1.0/search"
    response = requests.put(url, json=payload)
    dict_resp = json.loads(response.content)
    # print dict_resp
    resp = make_response(render_template('searchdogresults.html', results=dict_resp["dogs"]))
    return resp

### Search for a dog by providing its unique ID
@app.route('/dogbyid') # search page which submits to viewdog
def dogbyid():
    resp = make_response(render_template('dogbyid.html'))
    return resp

### View full dog details by providing its unique ID
@app.route('/viewdog')
def viewdog():

    global username
    userid = "admin"

    dogid = request.args.get('dogid')
    url = dog_api + "/api/v1.0/dog/" + dogid
    response = requests.get(url)
    dict_resp = json.loads(response.content)

    photo = "http://" + namespace + ".public.ecstestdrive.com/" + bname + "/" + dogid + ".jpg"
    qrcode = "http://" + namespace + ".public.ecstestdrive.com/" + bname + "/" + dogid + "-qr.jpg"

    resp = make_response(render_template('viewdog.html', dogid=dogid, dog_details=dict_resp["dog"], photo=photo, qrcode=qrcode))
    return resp

def str2bool(v):
    return v.lower() in ("true")

### Add dog functions: GET and POST
@app.route('/adddog')
def adddog():
    resp = make_response(render_template('newdog.html'))
    return resp

@app.route('/adddogprocess.html', methods=['POST'])
def adddogprocess():

    dog_details = request.form.to_dict()
    # The value of radio buttons are returned as strings. The API expects them in Bool
    dog_details["reg_status"] = str2bool(dog_details["reg_status"])
    dog_details["vacc_status"] = str2bool(dog_details["vacc_status"])
    print dog_details

    # Call the dog service to insert it and get a dogid back
    url = dog_api + "/api/v1.0/dog"
    api_resp = requests.post(url, json=dog_details)
    print api_resp.content
    dict_resp = json.loads(api_resp.content)
    dogid = dict_resp["dog"]["id"]

    ## Now we can upload the photo with a name based on dogid
    myfile = request.files['file']
    # First get the file name and see if it's secure
    if myfile and allowed_file(myfile.filename):
        upload_file(myfile, dogid + ".jpg")
    # This is how will be reached
    photo = "http://" + namespace + ".public.ecstestdrive.com/" + bname + "/" + dogid + ".jpg"

    # Create the QRcode and upload to ECS
    upload_file(qrgen(dogid), dogid + "-qr.jpg")
    qrcode = "http://" + namespace + ".public.ecstestdrive.com/" + bname + "/" + dogid + "-qr.jpg"

    resp = make_response(render_template('dogregistered.html', dogid=dogid, dog_details=dog_details, photo=photo, qrcode=qrcode))
    return resp

### Delete dog: GET and POST
@app.route('/deldog')
def deldog():
    resp = make_response(render_template('deldog.html'))
    return resp

@app.route('/deldogprocess.html', methods=['POST'])
def deldogprocess():

    dogid = request.form['dogid']
    ## We should read dog details, display them for confirmation
    ## ... but for now let's keep it simple. Proceed with the deletion, right away
    url = dog_api + "/api/v1.0/dog/" + dogid
    api_resp = requests.delete(url)

    resp = make_response(render_template('dogdeleted.html', dogid=dogid))
    return resp

### Edit dog. It's a 3 step workflow:
#   1 - What dog you want edit (GET)
#   2 - This is the current information (POST)
#   3 - Let me save it for you (POST)
@app.route('/editdog')
def editdog():
    dogid = ""
    dogid = request.args.get('dogid')
    resp = make_response(render_template('editdog.html', dogid=dogid))
    return resp

@app.route('/editdogshowcurrent.html', methods=['GET','POST'])
def editdogshowcurrent():

    if request.method == 'GET':
        dogid = request.args.get('dogid')

    if request.method == 'POST':
        dogid = request.form['dogid']

    ## Now we call the dog service to read the details of that dog
    url = dog_api + "/api/v1.0/dog/" + dogid
    api_resp = requests.get(url)
    dict_resp = json.loads(api_resp.content)
    # The response is formatted as { "dog" : {"name":"Rufus"}, {},...}
    dog_to_edit = dict_resp["dog"]
    print dog_to_edit
    photo = "http://" + namespace + ".public.ecstestdrive.com/" + bname + "/" + dogid + ".jpg"

    resp = make_response(render_template('currentdog.html', dogid=dogid, dog_details=dog_to_edit, photo=photo))
    return resp

@app.route('/editdogapplychanges.html', methods=['POST'])
def editdogapplychanges():

    dog_details = request.form.to_dict()
    # The value of radio buttons are returned as strings. The API expects them in Bool
    dog_details["reg_status"] = str2bool(dog_details["reg_status"])
    dog_details["vacc_status"] = str2bool(dog_details["vacc_status"])
    print("DOG DETAILS: %s" % dog_details)

    # Call the dog service to insert it and get a dogid back
    dogid = request.form['dogid']
    url = dog_api + "/api/v1.0/dog/" + dogid
    api_resp = requests.put(url, json=dog_details)
    dict_resp = json.loads(api_resp.content)
    print dict_resp["dog"]

    ## Let's upload the photo
    myfile = request.files['file']
    print "The file is: "
    print myfile
    # First get the file name and see if it's secure
    if myfile and allowed_file(myfile.filename):
        upload_file(myfile, dogid + ".jpg")

    photo = "http://" + namespace + ".public.ecstestdrive.com/" + bname + "/" + dogid + ".jpg"

    resp = make_response(render_template('dogmodified.html', dogid=dogid, dog_details=dict_resp["dog"], photo=photo))
    return resp

##########################
# Handler-related routes #
##########################

### Menu of handler available actions
@app.route('/handlers')
def handlers():
    resp = make_response(render_template('handlers.html', userstatus=userstatus))
    return resp

@app.route('/handlerbyid') # search page which submits to viewhandler
def handlerbyid():
    resp = make_response(render_template('handlerbyid.html'))
    return resp

@app.route('/searchhandler') # search page which submits to viewhandler
def searchhandler():
    # resp = make_response(render_template('searchhandler.html', viewhandler="viewhandler"))
    resp = make_response(render_template('searchhandler.html'))
    return resp

@app.route('/searchhandlerresults', methods=['POST'])
def searchhandlerresults():

    criteria = request.form['criteria']
    match = request.form['match'].lower()
    print "Searching for {} = {}".format(criteria.lower(), match.lower())
    # Convert True/False strings to boolean as required by API
    payload = {criteria : match}
    # print payload
    url = handler_api + "/api/v1.0/search"
    response = requests.put(url, json=payload)
    dict_resp = json.loads(response.content)
    # print dict_resp

    resp = make_response(render_template('searchhandlerresults.html', results=dict_resp["handlers"]))
    return resp

# displays result of Handler ID search in searchhandler
@app.route('/viewhandler')
def viewhandler():

    h_id = request.args.get('h_id')
    url = handler_api + "/api/v1.0/handler/" + h_id

    response = requests.get(url)
    dict_resp = json.loads(response.content)
    print dict_resp["handler"]

    resp = make_response(render_template('viewhandler.html', handlerinfo=dict_resp["handler"], h_id=h_id))
    return resp

### Add dog functions: GET and POST
@app.route('/addhandler')
def addhandler():
    resp = make_response(render_template('newhandler.html'))
    return resp

@app.route('/addhandlerprocess.html', methods=['POST'])
def addhandlerprocess():

    handler_details = request.form.to_dict()
    print handler_details

    # Call the dog service to insert it and get a dogid back
    url = handler_api + "/api/v1.0/handler"
    api_resp = requests.post(url, json=handler_details)
    dict_resp = json.loads(api_resp.content)
    h_id = dict_resp["handler"]["id"]

    resp = make_response(render_template('handlerregistered.html', h_id=h_id, handler_details=handler_details))
    return resp

### Delete dog: GET and POST
@app.route('/delhandler')
def delhandler():
    h_id = ""
    h_id = request.args.get('h_id')
    resp = make_response(render_template('delhandler.html', h_id=h_id))
    return resp

@app.route('/delhandlerprocess.html', methods=['POST'])
def delhandlerprocess():

    i = request.form['h_id']
    ## We should read handler details, display them for confirmation
    ## ... but for now let's keep it simple. Proceed with the deletion, right away
    url = handler_api + "/api/v1.0/handler/" + i
    api_resp = requests.delete(url)

    resp = make_response(render_template('handlerdeleted.html', h_id=i))
    return resp

### Delete handler
@app.route('/edithandler')
def edithandler():
    h_id = ""
    h_id = request.args.get('h_id')
    resp = make_response(render_template('edithandler.html', h_id=h_id))
    return resp

@app.route('/edithandlershowcurrent.html', methods=['GET','POST'])
def edithandlershowcurrent():

    if request.method == 'POST':
        h_id = request.form['h_id']

    ## Now we call the dog service to read the details of that dog
    url = handler_api + "/api/v1.0/handler/" + h_id
    api_resp = requests.get(url)
    dict_resp = json.loads(api_resp.content)

    handler_to_edit = dict_resp["handler"]
    print handler_to_edit

    resp = make_response(render_template('currenthandler.html', h_id=h_id, handler_details=handler_to_edit))
    return resp

@app.route('/edithandlerapplychanges.html', methods=['POST'])
def edithandlerapplychanges():

    handler_details = request.form.to_dict()
    print("HANDLER DETAILS: %s" % handler_details)
    h_id = request.form['h_id']

    url = handler_api + "/api/v1.0/handler/" + h_id
    api_resp = requests.put(url, json=handler_details)
    print("API_RESP: %s" % api_resp)
    dict_resp = json.loads(api_resp.content)

    resp = make_response(render_template('handlermodified.html', handler_details=handler_details))

    return resp

##################################
# External verification function #
# Intended for Service Providers #
##################################

@app.route('/verify/<dogid>', methods=["GET"])
def verify(dogid):
    # Get the dogid from the URL and call the dogs service
    url = dog_api + "/api/v1.0/dog/" + dogid
    dog_response = requests.get(url)

    # Extract dog details from response and get the id of its handler
    dog_dict = json.loads(dog_response.content)
    #print dog_dict["h_id"]

    # We can pull the details for the handler now
    url = handler_api + "/api/v1.0/handler/" + dog_dict["dog"]["handler_id"]
    handler_response = requests.get(url)

    # Extract handler details
    handler_dict = json.loads(handler_response.content)

    # Select data to be presented
    #print dog_dict["dog"]["name"]
    #print dog_dict["dog"]["pedigree"]
    #print "we will use " + dogid + " to pull the photo from ECS "
    #print handler_dict["handler"]["first_name"]
    # print "we can use " + dog_dict["dog"]["handler_id"] + " to pull the photo from ECS "
    dog_photo = "http://" + namespace + ".public.ecstestdrive.com/" + bname + "/" + dogid + ".jpg"
    handler_name = handler_dict["handler"]["first_name"] + " " + handler_dict["handler"]["last_name"]

    resp = make_response(render_template('verify.html', name=dog_dict["dog"]["name"],\
                    pedigree=dog_dict["dog"]["pedigree"], registration_id=dog_dict["dog"]["registration_id"],\
                    handler_name=handler_name, dog_photo=dog_photo))
    return resp

## This is the API version, to allow PetCo to print badges
## If we add an API gateway it should be expose there instead
@app.route('/api/v1/verify/<dogid>', methods=["GET"])
def apiverify(dogid):
    # Get the dogid from the URL and call the dogs service
    url = dog_api + "/api/v1.0/dog/" + dogid
    dog_response = requests.get(url)

    # Extract dog details from response and get the id of its handler
    dog_dict = json.loads(dog_response.content)
    print dog_dict

    # We can pull the details for the handler now
    url = handler_api + "/api/v1.0/handler/" + dog_dict["dog"]["handler_id"]
    handler_response = requests.get(url)

    # Extract handler details
    handler_dict = json.loads(handler_response.content)

    dog_photo = "http://" + namespace + ".public.ecstestdrive.com/" + bname + "/" + dogid + ".jpg"
    handler_name = handler_dict["handler"]["first_name"] + " " + handler_dict["handler"]["last_name"]

    payload = {
        "name" : dog_dict["dog"]["name"],
        "pedigree" : dog_dict["dog"]["pedigree"],
        "handler_name" : handler_name,
        "dog_photo" : dog_photo,
        "registration_id" : dog_dict["dog"]["registration_id"]
    }
    return jsonify( { 'dog': payload } )


############################
# ECS and QRcode functions #
############################

def upload_file(myfile, fname):
    # Save it locally to the "/uploads" directory. Don't forget to create the DIR !!!
    myfile.save(os.path.join("uploads", fname))
    # Now let's upload it to ECS
    print "Uploading " + fname + " to ECS"
    k = b.new_key(fname)
    k.set_contents_from_filename("uploads/" + fname)
    k.set_acl('public-read')
    # Finally remove the file from our container. We don't want to fill it up ;-)
    os.remove("uploads/" + fname)
    return

def qrgen(dogid):
    URL = ui_url + "/verify/" + dogid
    img = qrcode.make(URL)
    return img

def upload_doc(myfile, fname):
    # Save it locally to the "/uploads" directory. Don't forget to create the DIR !!!
    myfile.save(os.path.join("uploads", fname))
    # Now let's upload it to ECS
    print "Uploading " + fname + " to ECS"
    k = docadmin_s3.new_key(fname)
    k.set_contents_from_filename("uploads/" + fname)
    k.set_acl('public-read')
    # Finally remove the file from our container. We don't want to fill it up ;-)
    os.remove("uploads/" + fname)
    return

if __name__ == "__main__":
	app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', '5030')), threaded=True)
