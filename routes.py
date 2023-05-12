from app import app, db
from flask import request, render_template, flash, redirect,url_for, make_response
from flask_login import current_user, login_user, logout_user,login_required
from sqlalchemy import or_, and_
from models import *
from forms import *
from werkzeug.urls import url_parse
import secrets
from datetime import datetime, timedelta
import smtplib

AUTO_MAIL = 'noreply.teamlabomba@gmail.com'

def send_email_utility(subject,message,sender_email,recipient_email):
    # connect to SMTP server
    with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        
        # log in to SMTP server
        smtp.login('noreply.teamlabomba@gmail.com', 'kwwgipbddkuuutjy')

        
        # create email message
        email_message = f'Subject: {subject}\n\n{message}'
        
        # send email
        smtp.sendmail(sender_email, recipient_email, email_message)
   
    
with app.app_context():

    db.create_all()
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin",_is_admin=True)
        admin.set_password("admin")
        db.session.add(admin)
        db.session.commit()

@app.route('/login', methods=['GET', 'POST'])
def login():
  #check if current_user logged in, if so redirect to a page that makes sense
    if current_user.is_authenticated:
        return redirect(url_for('index'))   
    
    form = LoginForm()


    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user is None or not user.check_password(form.password.data):
            flash("Invalid username or password")
            return redirect(url_for('login'))
        
  
        
        login_user(user,remember=form.remember_me.data)
        next_page = request.args.get('next')
    
        if not next_page or url_parse(next_page).netloc != '':
            if not user._is_admin:
                next_page = url_for('user_home',username = user.username)
            else:
                next_page = url_for('admin_home',username = user.username)
            
        return redirect(next_page)

                 
    return render_template('login.html', title='Sign In', form=form)


# Temporary storage for password reset requests
password_reset_requests = {}

# Form for password reset request
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data
        if email not in [u.email for u in User.query.all()]:
            flash(f'There is no user registered with {email}!')
            return redirect(url_for('login'))


        # Generate a unique token
        token = secrets.token_hex(16)
        # Store the token in the temporary database
        password_reset_requests[token] = {'email': email, 'timestamp': datetime.now()}
        # Send an email to the user with the password reset link
        # You'll need to replace the placeholders with your own values
        send_email_utility('Password reset', f'Click the following link to reset your password: {url_for("reset_password", token=token, _external=True)}',AUTO_MAIL,email)
              
        flash('An email has been sent to your account with further instructions.')
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html',form=form)


# Form for resetting the password
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Check if the token is valid and hasn't expired
    if token not in password_reset_requests:
        flash(f'The token is invalid!')
        return redirect(url_for('login'))

    request_data = password_reset_requests[token]
    print(request_data)
    if datetime.now() - request_data['timestamp'] > timedelta(minutes=5):
        # Expired token
        del password_reset_requests[token]
        flash(f'Token has expired. Retry a new password reset request!')
        return redirect(url_for('login'))
   
    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Update the user's password in the database 
        user_changing_pwd =User.query.filter_by(email=request_data['email']).first()
        # You'll need to replace this with your own code to update the user's password
        user_changing_pwd.set_password(form.password.data)
        db.session.commit()
        # Delete the token from the temporary database
        del password_reset_requests[token]
        flash(f'Password reset succesful!')
        return redirect(url_for('login'))

    return render_template('reset_password.html',form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
  #check if current_user logged in, if so redirect to a page that makes sense
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user_check = User.query.filter(or_(User.email==form.email.data, User.username==form.username.data)).first()
        if user_check:
            if user_check.email == form.email.data:
                flash('The email already exist, please register under different email!')
            if user_check.username == form.username.data:
                flash('The username already exist, please register under different username!')

            return redirect(url_for('register'))

        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')
        return redirect(url_for('login'))

    return render_template('register.html', title='Register', form=form)


@app.route('/new_user', methods=['GET', 'POST'])
@login_required
def new_user():

    form = RegistrationForm()
    if form.validate_on_submit():
        user_check = User.query.filter(or_(User.email==form.email.data, User.username==form.username.data)).first()
        if user_check:
            flash('The user already exists, please register under different email and/or username!')
            return redirect(url_for('new_user'))
        
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')
        return redirect(url_for('admin_home',username = user.username))

    return render_template('new_user.html', title='Register new user', form=form)

@app.route('/new_trip/<int:user_id>',methods=['GET', 'POST'])
@login_required
def new_trip(user_id):
    form = NewTripForm()
    if form.validate_on_submit():
        trip = Trip(tripname=form.tripname.data,speed=form.speed.data,
                    distance=form.distance.data,elevation=form.elevation.data,
                    prestige = int(form.prestige.data),description=form.description.data,user_id=user_id,n_of_partecipants=form.n_of_partecipants.data)
       
        trip.score = Trip.calculate_score(trip.speed,trip.distance,trip.elevation,trip.prestige,trip.n_of_partecipants,[])
        db.session.add(trip)
        db.session.commit()
        flash('New trip registered!')
        if user_id == current_user.id:
            return redirect(url_for('user_home',username = current_user.username))
        else:
            return redirect(url_for('view_user_profile_by_TL',user_id=user_id))
    return render_template('new_trip.html',title="Add new trip", form = form )

@app.route('/user_home/<username>',methods=['GET', 'POST'])
@login_required
def user_home(username):
    
    user = User.query.filter_by(username=current_user.username).first()
    #trips = Trip.query.filter_by(user_id=current_user.id).all()
    teams = Team.query.all()
    message = ""
    """if user_teams:
        if user in team.users and RequestsToJoinTeam.query.filter_by(team_id = team.id).all():
            message = "You have some pending enrollment requests, check out the team page!"
    """
    #if trips is None:
    #    trips = []
    if teams is None:
        teams = []


    return render_template('user_home.html', user=user,teams=teams,new_enrollments=message)


@app.route('/admin_home/<username>',methods=['GET', 'POST'])
@login_required
def admin_home(username):
    
    users = User.query.filter(User._is_admin==None).all()
    trips = Trip.query.all()
    teams = Team.query.all()


    if trips is None:
        trips = []
    if teams is None:
        teams = []
    if users is None:
        users = []

    return render_template('admin_home.html', users=users,trips=trips,teams=teams)




@app.route('/user_profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    user = User.query.get(current_user.id)
    form = ProfileForm(obj=user)
    if form.validate_on_submit():
        form.populate_obj(user)
        db.session.commit()
        flash('Your profile has been updated!', 'success')
        return redirect(url_for('user_profile'))
    return render_template('user_profile.html', form=form)

@app.route("/edit_trip/<int:trip_id>/<int:user_id>", methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id,user_id):
    trip = Trip.query.get(trip_id)
    form = NewTripForm(obj=trip)
    if form.validate_on_submit():
        form.populate_obj(trip)
        trip.score = Trip.calculate_score(trip.speed,trip.distance,trip.elevation,int(trip.prestige),trip.n_of_partecipants,[])
        db.session.commit()
        flash('Your trip has been updated!', 'success')
        if user_id == current_user.id:
            return redirect(url_for('user_home',username=current_user.username))
        else:
            return redirect(url_for("view_user_profile_by_TL",user_id=user_id))
    return render_template('edit_trip.html', form=form,trip_id=trip.id,user_id=user_id)

@app.route('/')
def index():
    if not current_user.is_anonymous:
        return redirect(url_for('user_home',username=current_user.username))

    return render_template('landing_page.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route("/view_user_profile_by_TL/<int:user_id>")
@login_required
def view_user_profile_by_TL(user_id):
    user = User.query.get(user_id)
    trips = Trip.query.filter_by(user_id=user_id).all()
    teams= Team.query.all()
    return render_template("view_user_profile_by_TL.html",user=user,trips=trips,teams=teams)
 

@app.route("/delete_trip/<int:trip_id>/<int:user_id>")
@login_required
def delete_trip(trip_id,user_id):
    trip = Trip.query.filter_by(id=trip_id).first()
    db.session.delete(trip)
    db.session.commit()
    if user_id == current_user.id:
        return redirect(url_for('user_home',username=current_user.username))
    else:
        return redirect(url_for("view_user_profile_by_TL",user_id=user_id))

@app.route("/delete_team/<int:team_id>")
@login_required
def delete_team(team_id):
    team = Team.query.filter_by(id=team_id).first()
    db.session.delete(team)
    db.session.commit()
    return redirect(url_for("admin_home",username=current_user.username))

@app.route("/delete_user/<int:user_id>")
@login_required
def delete_user(user_id):
    user = User.query.filter_by(id=user_id).first()
    db.session.delete(user)
    db.session.commit()
    if current_user._is_admin:
        return redirect(url_for("admin_home",username=current_user.username))
    else:
        return redirect(url_for("index"))
    
@app.route("/trip_details/<int:trip_id>")
@login_required
def trip_details(trip_id):
    trip = Trip.query.get(trip_id)
    return render_template("trip_details.html",trip=trip)


@app.route("/team_details/<int:team_id>")
@login_required
def team_details(team_id):
    team = Team.query.get(team_id)
    members_by_team = User.query.filter(User.id.in_([member.id for member in team.users])).all()
    ranking_list = []
    requests_to_join = []
    requests_to_join_tl = []

    for user_by_team in members_by_team:
        all_scores_by_user = Trip.query.filter_by(user_id=user_by_team.id).all()
        tot_score_by_user =sum([score_by_user.score for score_by_user in all_scores_by_user])
        ranking_list.append({"user_id":user_by_team.id,"user":user_by_team.username,"total score":tot_score_by_user})
    ranking_list = list(enumerate(sorted(ranking_list, key=lambda x: x['total score'],reverse=True)))
    """
    if current_user.role =="user":
        if current_user not in members_by_team:
            requests_to_join = RequestsToJoinTeam.query.filter(and_(RequestsToJoinTeam.user_id==current_user.id, RequestsToJoinTeam.team_id == team_id)).first()

    if current_user.role =="team_leader":
        requests_to_join_tl = RequestsToJoinTeam.query.filter_by(team_id=team_id).all()
        requests_to_join_tl = [{"id":request_to_join.id,"user_id":User.query.get(request_to_join.user_id).id,"username":User.query.get(request_to_join.user_id).username} for request_to_join in requests_to_join_tl] 
    """
    return render_template("team_details.html",ranking_list=ranking_list,team=team,user=current_user, requests_to_join=requests_to_join,requests_to_join_tl=requests_to_join_tl)

@app.route('/new_team',methods=['GET', 'POST'])
@login_required
def new_team():
    if not current_user._is_admin:
        return 'Unauthorized'

    form = NewTeamForm()
    if form.validate_on_submit():
        team = Team(name=form.name.data,description=form.description.data)
       
        db.session.add(team)
        db.session.commit()
        flash('New team registered!')
        return redirect(url_for('admin_home',username = current_user.username))

    return render_template('new_team.html',title="Add new team", form = form )



@app.route('/manage_team',methods=['GET', 'POST'])
@login_required
def manage_team():
    try:
        team = User.query.filter_by(id=current_user.id).first().teams[0]
        team_members = [member for member in team.members if member.id != current_user.id]
        return render_template('manage_team.html',title="Manage team",team = team,users=team_members)
    except:
        if not current_user._is_admin:
            return redirect(url_for('user_home',username = current_user.username))
        else:
            return redirect(url_for('admin_home',username = current_user.username))

 
@app.route('/request_enrollment_to_team/<int:team_id>',methods=['GET', 'POST'])
@login_required
def request_enrollment_to_team(team_id):
    
    team = Team.query.get(team_id)
    user_req= RequestsToJoinTeam.query.filter_by(team_id = team_id, user_id = current_user.id).first()
    if user_req:
        return redirect(url_for("team_details",team_id=team_id))

    req = RequestsToJoinTeam(team_id = team_id,user_id = current_user.id,status="pending",request_date=datetime.now())
    if current_user not in team.users:
        db.session.add(req)
        db.session.commit()

        return redirect(url_for("team_details",team_id=team_id,requests_to_join=req))

@app.route('/withdraw_request_enrollment/<int:request_id>/<int:team_id>',methods=['GET', 'POST'])
@login_required
def withdraw_request_enrollment(request_id,team_id):
    
    request_to_remove = RequestsToJoinTeam.query.get(request_id)
    db.session.delete(request_to_remove)
    db.session.commit()

    return redirect(url_for("team_details",team_id=team_id))


@app.route('/decide_on_enrollment/<int:request_id>/<accept>',methods=['GET', 'POST'])
@login_required
def decide_on_enrollment(request_id,accept):
    
    request_to_join = RequestsToJoinTeam.query.get(request_id)
    if accept=="Yes":
        user = User.query.get(request_to_join.user_id)
        team = Team.query.get(request_to_join.team_id)
        team.add_member(user,role="user")
        db.session.delete(request_to_join)
        db.session.commit()
    else:
        db.session.delete(request_to_join)
        db.session.commit()
    
    return redirect(url_for("user_home",username=current_user.username))


@app.route('/enroll_directly/<int:team_id>/<int:user_id>',methods=['GET', 'POST'])
@login_required
def enroll_directly(team_id,user_id):
    
    user = User.query.get(user_id)
    team = Team.query.get(team_id)
    team.add_member(user,role="user")

    db.session.commit()

    eventual_requests_to_eliminate =  RequestsToJoinTeam.query.filter(and_(RequestsToJoinTeam.user_id==user.id,RequestsToJoinTeam.team_id==team.id)).all()
    [db.session.delete(req_to_eliminate) for req_to_eliminate in eventual_requests_to_eliminate]

    db.session.commit()

    
    return redirect(url_for("admin_home",username=current_user.username))

@app.route('/unenroll_from_team/<int:team_id>/<int:user_id>',methods=['GET', 'POST'])
@login_required
def unenroll_from_team(team_id,user_id):
    
    team =  Team.query.get(team_id)
    user = User.query.get(user_id)
    if current_user in team.users or user in team.users:
        user.set_role("user")
        team.users.remove(user)
        db.session.commit()
    
    return redirect(url_for("manage_team",username=current_user.username))


@app.route("/change_role",methods=['GET', 'POST'])
@login_required
def change_role():
    user_id = request.form.get('user_id')
    role = request.form.get('role')
    user = User.query.get(user_id)
    if role != user.role:
        user.set_role(role)
        db.session.commit()

    return redirect(url_for("manage_team", users = User.query.all()))