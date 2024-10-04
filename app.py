import random
import base64
import json
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from requests import post, get
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")

app = Flask(__name__)
app.secret_key = 'your_secret_key'

token = None
score = 0

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            highest_score INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def get_token():
    global token
    auth_string = client_id + ":" + client_secret
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

    url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": "Basic " + auth_base64,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    
    result = post(url, headers=headers, data=data)
    json_result = json.loads(result.content)
    token = json_result["access_token"]
    return token

def get_auth_header():
    return {"Authorization": "Bearer " + token}

def playlist():
    url = "https://api.spotify.com/v1/playlists/4cI8iMj6nLUTgAWLmdwAg4/tracks"
    headers = get_auth_header()
    
    artist_album_list = []
    
    while url:
        result = get(url, headers=headers)
        data = json.loads(result.content)
        
        for item in data['items']:
            if item['track']:
                track = item['track']
                preview_url = track.get('preview_url', None)
                if preview_url:
                    artist = track['artists'][0]['name']
                    album_cover = track['album']['images'][0]['url']
                    track_name = track['name']
                    artist_album_list.append({
                        'artist': artist,
                        'album': album_cover,
                        'track_name': track_name,
                        'preview_url': preview_url
                    })
        
        url = data['next']

    return artist_album_list

def new_game():
    global token
    lst = playlist()
    random.shuffle(lst)

    r = random.randint(0, len(lst) - 1)
    answer = lst[r]['track_name'] 
    preview_url = lst[r]['preview_url']
    artist_name = lst[r]['artist']
    album_cover = lst[r]['album']

    same_artist_tracks = [track for track in lst if track['artist'] == artist_name and track['track_name'] != answer]

    options = [lst[r]]

    if len(same_artist_tracks) >= 2:
        other_options = random.sample(same_artist_tracks, 2)
    else:
        other_options = same_artist_tracks[:]
        
        other_tracks = [track for track in lst if track['track_name'] != answer]

        while len(other_options) < 2 and other_tracks:
            random_track = random.choice(other_tracks)
            if random_track not in other_options:
                other_options.append(random_track)
                other_tracks.remove(random_track)

        while len(other_options) < 2 and other_tracks:
            random_track = random.choice(other_tracks)
            if random_track not in other_options:
                other_options.append(random_track)
                other_tracks.remove(random_track)

    options.extend(other_options)

    if len(options) > 3:
        options = random.sample(options, 3)

    random.shuffle(options)

    choices = [option['track_name'] for option in options]

    return {
        'album': album_cover,
        'choices': choices,
        'answer': answer,
        'preview_url': preview_url
    }


get_token()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()

        if user:
            if user[2] == password:
                session['user_id'] = user[0]
                return redirect(url_for('game'))
            else:
                flash('Incorrect password entered', 'danger')
        else:
            cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
            session['user_id'] = cursor.lastrowid
            return redirect(url_for('game'))

        conn.close()
    
    return render_template('index.html')

@app.route('/start')
def start():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return redirect(url_for('game'))

@app.route('/game')
def game():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    global token
    global score
    score = 0
    current_game = new_game()
    return render_template('game.html', game=current_game, score=score, token=token)

@app.route('/guess', methods=['POST'])
def guess():
    global score
    user_choice = request.form['choice']
    correct_answer = request.form['answer']

    if user_choice == correct_answer:
        score += 1
        current_game = new_game()
        return render_template('game.html', game=current_game, score=score, token=token)
    else:
        highest_score = update_highest_score()
        return redirect(url_for('loss', score=score, highest_score=highest_score))

@app.route('/loss')
def loss():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, highest_score FROM users WHERE id = ?', (user_id,))
    user_info = cursor.fetchone()
    conn.close()

    username = user_info[0]
    highest_score = user_info[1]

    return render_template('loss.html', score=score, username=username, highest_score=highest_score)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

def update_highest_score():
    global score
    user_id = session.get('user_id')

    if user_id is not None:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT highest_score FROM users WHERE id = ?', (user_id,))
        highest_score = cursor.fetchone()[0]

        if score > highest_score:
            cursor.execute('UPDATE users SET highest_score = ? WHERE id = ?', (score, user_id))
            conn.commit()
        
        conn.close()
        return highest_score
    return 0

@app.route('/leaderboard')
def leaderboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, highest_score FROM users ORDER BY highest_score DESC LIMIT 10')
    leaderboard_data = cursor.fetchall()
    conn.close()

    leaderboard = [{'username': row[0], 'highest_score': row[1]} for row in leaderboard_data]

    return render_template('leaderboard.html', leaderboard=leaderboard)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
