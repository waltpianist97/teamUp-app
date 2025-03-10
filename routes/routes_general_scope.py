from app import app, db
from flask import request, render_template, flash, redirect, url_for, send_from_directory
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import or_, and_, desc, func
from models import User, Trip, Team, TeamUserAssociation, RequestsToJoinTeam, PlacementsInTrip
from forms import *
from werkzeug.urls import url_parse
import secrets
from datetime import datetime, timedelta
import smtplib
from tools import AUTO_MAIL, send_email_utility
import os
from urllib.parse import unquote

DATE_FORMAT = "%d/%m/%Y"

# %% GENERAL
with app.app_context():

    db.create_all()
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", _is_admin=True)
        admin.set_password("admin")
        db.session.add(admin)
        db.session.commit()


@app.route('/')
def index():
    if not current_user.is_anonymous:
        return redirect(url_for('user_home', username=current_user.username))

    return render_template('landing_page.html')


@app.route('/new_trip/<int:user_id>', methods=['GET', 'POST'])
@app.route('/new_trip/<int:user_id>/<int:team_id>', methods=['GET', 'POST'])
@app.route('/new_trip/<int:user_id>/<act_name>/<float:act_speed>/<float:act_distance>/<float:act_elevation>/<act_date>/<int:act_id>', methods=['GET', 'POST'])
@login_required
def new_trip(user_id, team_id=None, act_name=None, act_speed=None, act_distance=None, act_elevation=None, act_date=None, act_id=None):
    form = NewTripForm()
    user = User.query.get(user_id)

    # handle strava api connection
    if act_name is not None and act_speed is not None and act_distance is not None and act_elevation is not None and act_date is not None:
        form.tripname.data = act_name
        form.speed.data = round(act_speed, 2)
        form.distance.data = act_distance
        form.elevation.data = act_elevation

        act_date = act_date.replace('-', '/')
        form.recorded_on.data = act_date

    if not team_id:
        if user == current_user:
            form.team.choices = [(team.id, team.name) for team in user.teams]
        else:
            form.team.choices = [(team.id, team.name)
                                 for team in user.teams if current_user in team.users]
    else:
        team_chosen = Team.query.get(team_id)
        form.team.choices = [(team_chosen.id, team_chosen.name)]
        form.team.data = team_chosen.id
        form.team.render_kw = {'disabled': 'disabled'}

    teams = Team.query.all()

    if request.method == "POST":

        try:
            recorded_on = datetime.strptime(form.recorded_on.data, DATE_FORMAT)
        except ValueError:
            # Invalid date format
            flash(
                "Data nel formato errato: per favore inserisci una data nel formato dd/mm/yyyy")
            return render_template('new_trip.html', title="Add new trip", form=form)

        trip = Trip(tripname=form.tripname.data, speed=form.speed.data, n_of_placements=form.n_of_placements.data,
                    distance=form.distance.data, elevation=form.elevation.data, team_id=form.team.data, recorded_on=recorded_on,
                    prestige=int(form.prestige.data), description=form.description.data, user_id=user_id, n_of_partecipants=form.n_of_partecipants.data, strava_id=act_id)

        db.session.add(trip)
        db.session.flush()  # Flush changes to assign an ID to the trip object

        placement_values = [int(pl)
                            for pl in request.form.getlist('placement[]')]

        for placement_value in placement_values:

            placement = PlacementsInTrip(
                trip_id=trip.id, place=placement_value)
            db.session.add(placement)

        trip.score = Trip.calculate_score(
            trip.speed, trip.distance, trip.elevation, trip.prestige, trip.n_of_partecipants, placement_values)

        t_r = TeamUserAssociation.query.filter(and_(
            TeamUserAssociation.user_id == user.id, TeamUserAssociation.team_id == form.team.data)).first().role

        if t_r in ["team_leader", "deputy"]:
            trip.is_approved = True
        else:
            trip.is_approved = False

        db.session.commit()
        flash('Nuovo giro registrato!')

        team = Team.query.get(trip.team_id)

        if t_r not in ["team_leader", "deputy"]:
            emails_leaders = [tl.email for tl in team.get_leaders()]
            emails_deputies = [td.email for td in team.get_deputies()]

            send_email_utility('Richiesta approvazione giro',
                               f"{user.username} ha richiesto di registrare il giro: {trip.tripname} per il team {trip.get_team().name}, controlla la tua pagina 'Gestisci giri'!", AUTO_MAIL, emails_leaders+emails_deputies)
        else:
            other_members_emails = [
                user.email for user in team.users if trip.get_user() != user]
            if other_members_emails:
                send_email_utility(
                    "Registrazione nuovo giro", f"Il giro: {trip.tripname} di {trip.get_user().username} e' stato registrato per il team {trip.get_team().name}", AUTO_MAIL, other_members_emails)
            _ = team.ranking_builder()

        if user == current_user:
            return redirect(url_for('trips_overview', user_id=user.id))
        else:
            return redirect(url_for('member_home', team_id=form.team.data, user_id=user.id))

    return render_template('new_trip.html', title="Add new trip", form=form, teams=teams)


@app.route('/images/<path:filepath>', methods=['GET', 'POST'])
def serve_image(filepath):
    directory = 'images'
    full_path = os.path.join(directory, filepath)

    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))


@app.route("/edit_trip/<int:trip_id>/<int:user_id>", methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id, user_id):
    trip = Trip.query.get(trip_id)
    placements = trip.get_placements()
    user = User.query.get(user_id)
    user_role_in_team = user.get_role_in_team(trip.team_id)
    form = NewTripForm(obj=trip)
    trip_team = Team.query.get(trip.team_id)
    form.team.choices = [(trip_team.id, trip_team.name)]
    form.team.render_kw = {'disabled': 'disabled'}
    form.recorded_on.data = trip.recorded_on.strftime(DATE_FORMAT)
    teams = Team.query.all()

    if request.method == 'POST':

        [db.session.delete(placement) for placement in placements]
        db.session.commit()

        trip.tripname = request.form["tripname"]
        trip.speed = float(request.form["speed"])
        trip.distance = float(request.form["distance"])
        trip.elevation = float(request.form["elevation"])
        trip.prestige = int(request.form["prestige"])
        trip.description = request.form["description"]
        trip.n_of_partecipants = int(request.form["n_of_partecipants"])
        placement_values = [int(pl)
                            for pl in request.form.getlist('placement[]')]
        edit_placements = [int(pl)
                           for pl in request.form.getlist('edit_placement')]
        placement_ids = request.form.getlist('placement_id')

        try:
            trip.recorded_on = datetime.strptime(
                request.form["recorded_on"], DATE_FORMAT)
        except ValueError:
            # Invalid date format
            return render_template('edit_trip.html', form=form, trip_id=trip.id, user_id=user_id, my_role_in_team=user_role_in_team, is_approved=trip.is_approved, placements=placements)

        if edit_placements:
            for id, place in zip(placement_ids, edit_placements):
                placement = PlacementsInTrip(
                    id=id, trip_id=trip.id, place=int(place))
                db.session.add(placement)

        for placement_value in placement_values:
            placement = PlacementsInTrip(
                trip_id=trip.id, place=int(placement_value))
            db.session.add(placement)

        trip.score = Trip.calculate_score(trip.speed, trip.distance, trip.elevation,
                                          trip.prestige, trip.n_of_partecipants, placement_values+edit_placements)

        db.session.commit()

        flash("Il giro e stato aggiornato!", 'success')

        if trip.get_user() != current_user and current_user in trip.get_team().get_leaders():
            send_email_utility(
                'Modifica giro', f"Il tuo giro e' stato modificato dal team leader {current_user.username}", AUTO_MAIL, trip.get_user().email)

        trip_team = trip.get_team()
        _ = trip_team.ranking_builder()

        my_role_in_team = current_user.get_role_in_team(trip.team_id)
        if my_role_in_team in ["team_leader", "deputy"]:
            return redirect(url_for('manage_trips', team_id=trip.team_id))
        else:
            return redirect(url_for('trips_overview', user_id=current_user.id))

    return render_template('edit_trip.html', form=form, trip_id=trip.id, user_id=user_id, my_role_in_team=user_role_in_team, is_approved=trip.is_approved, placements=placements, teams=teams)


@app.route("/delete_trip/<int:trip_id>/<int:user_id>")
@login_required
def delete_trip(trip_id, user_id):
    trip = Trip.query.filter_by(id=trip_id).first()
    db.session.delete(trip)
    db.session.commit()
    flash("Il giro e' stato eliminato!")
    if user_id == current_user.id:
        return redirect(url_for('trips_overview', user_id=current_user.id))
    else:
        return redirect(url_for('manage_trips', team_id=trip.team_id))


# %% LOGIN SECTION
@app.route('/login', methods=['GET', 'POST'])
def login():
  # check if current_user logged in, if so redirect to a page that makes sense
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user is None or not user.check_password(form.password.data):
            flash("Username o password non validi")
            return redirect(url_for('login'))

        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')

        if not next_page or url_parse(next_page).netloc != '':
            if not user._is_admin:
                next_page = url_for('user_home', username=user.username)
            else:
                next_page = url_for('admin_home')

        return redirect(next_page)

    return render_template('login.html', title='Sign In', form=form)


# Temporary storage for password reset requests
password_reset_requests = {}
# Form for password reset request


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        user_recover = User.query.filter_by(username=username).first()
        if not user_recover:
            flash(f"Non esiste alcun \'{username}\' registrato nel sistema!")
            return redirect(url_for('login'))
        
        #if the password_reset_requests contains one request, clean up
        if password_reset_requests:
            password_reset_requests.clear()

        email = user_recover.email
        # Generate a unique token
        token = secrets.token_hex(16)


        # Store the token in the temporary database
        password_reset_requests[token] = {
            'email': email, 'timestamp': datetime.now()}
        # Send an email to the user with the password reset link
        # You'll need to replace the placeholders with your own values
        send_email_utility(
            'Password reset', f'Clicca il seguente link per resettare la tua password: {url_for("reset_password", token=token, _external=True)}', AUTO_MAIL, email)

        flash(
            "Una email e' stata inviata alla tua casella di posta con ulteriori istruzioni!")
        return redirect(url_for('login'))

# Form for resetting the password


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Check if the token is valid and hasn't expired
    if token not in password_reset_requests:
        flash("Il token non e' valido!")
        return redirect(url_for('login'))

    request_data = password_reset_requests[token]
    print(request_data)
    if datetime.now() - request_data['timestamp'] > timedelta(minutes=5):
        # Expired token
        del password_reset_requests[token]
        flash("Il token e' scaduto. Richiedere recupero password!")
        return redirect(url_for('login'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Update the user's password in the database
        user_changing_pwd = User.query.filter_by(
            email=request_data['email']).first()
        # You'll need to replace this with your own code to update the user's password
        user_changing_pwd.set_password(form.password.data)
        db.session.commit()
        # Delete the token from the temporary database
        del password_reset_requests[token]
        flash(f'Password reset avvenuto con successo!')
        return redirect(url_for('login'))

    return render_template('reset_password.html', form=form)


@app.route('/register', methods=['GET', 'POST'])
def register():
  # check if current_user logged in, if so redirect to a page that makes sense
    if current_user.is_authenticated and not current_user._is_admin:
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user_check = User.query.filter(
            or_(User.email == form.email.data, User.username == form.username.data)).first()
        if user_check:
            if user_check.email == form.email.data:
                flash("La mail email esiste gia', per favore scegli una mail diversa!")
            if user_check.username == form.username.data:
                flash("Lo username esiste gia', per favore scegli uno username diverso!")

            return redirect(url_for('register'))

        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        user.create_pictures_folder()

        db.session.add(user)
        db.session.commit()

        flash('Congratulazioni, ti sei registrato sulla piattaforma!')
        return redirect(url_for('login'))

    return render_template('register.html', title='Register', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))
