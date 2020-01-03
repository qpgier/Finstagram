# -*- coding: utf-8 -*-
"""
Created on Sun Nov 24 15:28:51 2019

@author: quing
"""

from flask import Flask, render_template, request, session, redirect, url_for, send_file
import os
import uuid
import hashlib
SALT = 'cs3083'
import pymysql.cursors
from functools import wraps
import time

app = Flask(__name__, static_url_path='')
app.secret_key = "super secret key"
IMAGES_DIR = os.path.join(os.getcwd(), "images")

connection = pymysql.connect(host="localhost",
                             user="root",
                             password="",
                             db="finsta",
                             charset="utf8mb4",
                             port=3306,
                             cursorclass=pymysql.cursors.DictCursor,
                             autocommit=True)

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if not "username" in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return dec

@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("home"))
    return render_template("index.html")

@app.route("/home")
@login_required
def home():
    return render_template("home.html", username=session["username"])

@app.route("/upload", methods=["GET"])
@login_required
def upload():
    return render_template("upload.html")


#Displays the images that are available to the current user
@app.route("/images", methods=["GET"])
@login_required
def images():
    cursor = connection.cursor()
    username = session["username"]
    queryView = "CREATE OR REPLACE VIEW photoinfo as SELECT * FROM photo WHERE photoPoster = %s OR photoId IN (SELECT photoID FROM sharedwith WHERE groupName IN (SELECT groupName FROM belongto WHERE member_username = %s)) OR photoID IN (SELECT photoID FROM photo WHERE allFollowers = 1 AND photoPoster IN (SELECT username_followed FROM follow WHERE username_follower = %s AND followStatus = 1))"
    cursor.execute(queryView, (username, username, username))
    queryinfo2 = "CREATE OR REPLACE VIEW names as SELECT firstname, lastname, username FROM person RIGHT JOIN photoinfo ON person.username = photoinfo.photoposter"
    cursor.execute(queryinfo2)
    queryinfo2 = "CREATE OR REPLACE VIEW info as SELECT DISTINCT * FROM photoinfo RIGHT OUTER JOIN names on photoinfo.photoposter = names.username GROUP BY photoID ORDER BY photoID desc"
    cursor.execute(queryinfo2)
    queryImages = "SELECT * FROM info"
    cursor.execute(queryImages)
    data = cursor.fetchall()
    return render_template("images.html", images=data)

@app.route("/image/<image_name>", methods=["GET"])
def image(image_name):
    image_location = os.path.join(IMAGES_DIR, image_name)
    if os.path.isfile(image_location):
        return send_file(image_location, mimetype="image/jpg")

@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")

@app.route("/register", methods=["GET"])
def register():
    return render_template("register.html")

@app.route("/loginAuth", methods=["GET", "POST"])
def loginAuth():
    #grabs information from the forms
    username = request.form['username']
    password = request.form['password'] + SALT
    hashed_password = hashlib.sha256(password.encode('utf-8')).hexdigest()

    #cursor used to send queries
    cursor = connection.cursor()
    #executes query
    query = 'SELECT * FROM person WHERE username = %s and password = %s'
    cursor.execute(query, (username, hashed_password))
    #stores the results in a variable
    data = cursor.fetchone()
    #use fetchall() if you are expecting more than 1 data row
    cursor.close()
    error = None
    if(data):
        #creates a session for the the user
        #session is a built in
        session['username'] = username
        return redirect(url_for('home'))
    else:
        #returns an error message to the html page
        error = 'Invalid login or username'
        return render_template('login.html', error=error)

@app.route("/registerAuth", methods=["POST"])
def registerAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPassword = requestData["password"]
        salted = plaintextPassword + SALT
        hashedPassword = hashlib.sha256(salted.encode("utf-8")).hexdigest()
        firstName = requestData["fname"]
        lastName = requestData["lname"]
        
        try:
            with connection.cursor() as cursor:
                query = "INSERT INTO person (username, password, firstname, lastname) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (username, hashedPassword, firstName, lastName))
        except pymysql.err.IntegrityError:
            error = "%s is already taken." % (username)
            return render_template('register.html', error=error)    

        return redirect(url_for("login"))

    error = "An error has occurred. Please try again."
    return render_template("register.html", error=error)

@app.route("/logout", methods=["GET"])
def logout():
    session.pop("username")
    return redirect("/")


#Allows the use to upload an image and dictate if they want to allow
#all followers to see it, choose which friendgroups, or keep it as private by 
#selecting Go BacK
@app.route("/uploadImage", methods=["GET", "POST"])
@login_required
def upload_image():
    if request.files:
        image_file = request.files.get("imageToUpload", "")
        image_name = image_file.filename
        shareWith = request.form.getlist("followers")
        userName = session["username"]
        allFollowers = bool 
        if shareWith[0] == "Yes":
                allFollowers = True
        else:
            allFollowers = False
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)
        query = "INSERT INTO photo (postingDate, filePath) VALUES (%s, %s)"
        with connection.cursor() as cursor:
            cursor.execute(query, (time.strftime('%Y-%m-%d %H:%M:%S'), image_name))
        query = "UPDATE photo SET allFollowers = %s WHERE filePath = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (allFollowers, image_name))
        query = "UPDATE photo SET photoPoster = %s WHERE filePath = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (userName, image_name))
        if allFollowers == True:
            message = "Image has been successfully uploaded."
            return render_template("upload.html", message=message)
        else:
            message = "Please enter the Group Name and Group Owner"
            return render_template("selectGroups.html", message=message)
    


#Implements the selection of which groups are allowed to see the photo
# The "sharewith"
@app.route("/selectGroups", methods = ["GET", "POST"])
@login_required
def selectGroups():
    if request.form:
        requestData = request.form
        cursor = connection.cursor()
        photoIDQuery = "SELECT max(photoID) FROM photo"
        cursor.execute(photoIDQuery)
        photoID = cursor.fetchall()
        photoID = photoID[0].get('max(photoID)')
        groupName = requestData["groupName"]
        groupOwner = requestData["groupOwner"]
        shareWithQuery = "INSERT INTO SharedWith (groupName, groupOwner, photoID) VALUES (%s, %s, %s)"
        existQuery = "SELECT groupName, groupOwner FROM friendgroup WHERE groupName = %s AND groupOwner = %s"
        cursor.execute(existQuery, (groupName, groupOwner))
        exist = cursor.fetchall()
        print (len(exist))
        if len(exist) == 0 :
            message = "That Group or Group Owner is incorrect, please try again"
            return render_template("selectGroups.html", message = message)
        else:
            cursor.execute(shareWithQuery, (groupName, groupOwner, photoID))
            return redirect(url_for("upload"))
    


#Page that visualizes which users have requested to follow the current user
@app.route('/manage')
@login_required
def manage():
    username = session['username']
    cursor = connection.cursor();

    query = 'SELECT * FROM Follow WHERE followStatus = 0 AND username_followed = %s'
    cursor.execute(query, (username))
    requestData = cursor.fetchall()


    cursor.close()
    return render_template('manage.html',requestData = requestData)


#runs within /manage, the queries that occur when the follow is accepted or denied
@app.route('/AcceptOrDecline', methods = ["GET", "POST"])
@login_required
def followAcceptOrDecline():
    username = session['username']
    username_follower = request.form['username_follower']
    if (request.form["followButton"] == "accept"):
        updateFollowQuery = 'UPDATE Follow SET followStatus = 1 WHERE username_followed = %s AND username_follower = %s'
        cursor = connection.cursor();
        cursor.execute(updateFollowQuery, (username, username_follower))

    else:
        (request.form["followButton"] == "decline")
        updateFollowQuery = 'DELETE FROM Follow WHERE username_followed = %s'
        cursor = connection.cursor();
        cursor.execute(updateFollowQuery, (username))
    query = 'SELECT * FROM Follow WHERE followStatus = 0 AND username_followed = %s'
    cursor.execute(query, (username))
    requestData = cursor.fetchall()


    cursor.close()
    return render_template('manage.html',requestData = requestData)


#On the home page, allows the user to input a username and request to follow them
@app.route("/follow", methods=["GET", "POST"])
def follow():
    username = session['username']
    poster = request.args['follow']
    print(poster)

    cursor = connection.cursor();
    if (username != poster):
        try:
            query = 'INSERT INTO Follow (username_follower, username_followed, followStatus) VALUES(%s, %s, %s)'
            cursor.execute(query, (username, poster, 0))
        except pymysql.err.IntegrityError:
            print("Could not find username")
    else:
        print("ERROR. TRYING TO FOLLOW YOURSELF!")

    return redirect(url_for('home'))


#Create a group webapage
@app.route("/createGroup", methods=["GET"])
def createGroup():
    return render_template("createGroup.html")


#From the creat a group webpage:
#allows the user to create a new friendgroup if they don't already have one by that name
@app.route("/createAGroup", methods=["GET","POST"])
def createTheGroup():
    username = session["username"]
    groupName = request.form['groupName']
    description = request.form['description']
    cursor = connection.cursor();
    querycheck = "SELECT groupName, groupOwner FROM friendgroup WHERE groupname = %s AND groupowner = %s"
    cursor.execute(querycheck, (groupName, username))
    check = cursor.fetchall()
    if len(check) == 0:
        query = "INSERT INTO friendGroup (groupName, groupOwner) VALUES (%s, %s)"
        cursor.execute(query, (groupName, username))
        if description == '':
            query = "UPDATE friendgroup SET description = False WHERE groupName = %s AND groupOwner = %s"
            cursor.execute(query, (groupName, username))
        else:
            query = "UPDATE friendgroup SET description = %s WHERE groupName = %s AND groupOwner = %s"
            cursor.execute(query, (description, groupName, username))
        message = "Group Created!"
        return render_template('createGroup.html',message=message)
    else:
        message = "That group already exists!"
        return render_template('createGroup.html',message=message)


#add to group webpage
@app.route("/addToGroup", methods=["GET"])
def addToGroup():
    return render_template("addToGroup.html")


#allows the user to add a person to a friendgroup if they are not already in it
@app.route("/addThisPerson", methods=["GET","POST"])
def addThisPerson():
    username = session["username"]
    groupName = request.form['groupName']
    userToAdd = request.form['username']
    cursor = connection.cursor();
    querycheck = "SELECT member_username, owner_username, groupName FROM belongto WHERE member_username = %s AND owner_username = %s AND groupName = %s"
    cursor.execute(querycheck, (userToAdd, username, groupName))
    check = cursor.fetchall()
    if len(check) == 0:
        query = "INSERT INTO belongto (member_username, owner_username, groupName) VALUES (%s, %s, %s)"
        cursor.execute(query, (userToAdd, username, groupName))
        message = "Your Friend Is Now In That Group!"
        return render_template("addToGroup.html",message=message)
    else:
        message = "That Friend Is Already In That Group!"
        return render_template("addToGroup.html",message=message)

if __name__ == "__main__":
    if not os.path.isdir("images"):
        os.mkdir(IMAGES_DIR)
    app.run()
  
