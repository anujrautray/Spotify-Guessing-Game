import random
import base64
import json
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from requests import post, get

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Ensure to use a strong secret key

CLIENT_ID = "your_client_id"
CLIENT_SECRET = "your_client_secret"

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
    auth_string = CLIENT_ID + ":" + CLIENT_SECRET
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
    return json_result["access_token"]

def get_auth_header(token):
    return {"Authorization": "Bearer " + token}

def playlist(token):
    url = "https://api.spotify.com/v1/playlists/4cI8iMj6nLUTgAWLmdwAg4/tracks"
    headers = get_auth_header(token)
    
    artist_album_list = []
    
    while url:
        result = get(url, headers=headers)
        data = json.loads(result.content)
        
        for item in data['items']:
            if item['track']:
                artist = item['track']['artists'][0]['name']
                album_cover = item['track']['album']['images'][0]['url']
                track_uri = item['track']['uri']  
                preview_url = item['track'].get('preview_url', None)
                artist_album_list.append({
                    'artist': artist,
                    'album': album_cover,
                    'track_uri': track_uri,
                    'preview_url': preview_url
                })
        
        url = data['next']

    return artist_album_list

def new_game(token):
    lst = playlist(token)
    if not lst:
        return None  # Return None if no tracks are available

    random.shuffle(lst)
    r = random.randint(0, len(lst) - 1)
    answer = lst[r]['track_name']  # Update this to use track name
    track_uri = lst[r]['track_uri']
    preview_url = lst[r].get('preview_url', None)

    # Filter tracks by the same artist
    same_artist_tracks = [track for track in lst if track['artist'] == lst[r]['artist']]
    if len(same_artist_tracks) < 3:
        # If less than 3, add a random track
        other_tracks = random.sample(lst, min(3 - len(same_artist_tracks), len(lst)))
        choices = same_artist_tracks + other_tracks
    else:
        choices = random.sample(same_artist_tracks, 2) + [lst[r]]  # 1 correct + 2 wrong

    random.shuffle(choices)  # Shuffle the choices

    return {
        'album': lst[r]['album'],
        'choices': [choice['track_name'] for choice in choices],
        'answer': answer,
        'track_uri': track_uri,
        'preview_url': preview_url
    }

# Call get_token once to initialize the token
token = get_token()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Check if the user exists
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()

        if user:
            if user[2] == password:
                session['user_id'] = user[0]
                session['score'] = 0  # Reset score for new game
                session['current_game'] = new_game(token)  # Initialize game
                return redirect(url_for('game'))
            else:
                flash('Incorrect password entered', 'danger')
        else:
            cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            conn.commit()
            session['user_id'] = cursor.lastrowid
            session['score'] = 0  # Reset score for new game
            session['current_game'] = new_game(token)  # Initialize game
            return redirect(url_for('game'))

        conn.close()
    
    return render_template('index.html')

@app.route('/game')
def game():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    return render_template('game.html', game=session['current_game'], score=session['score'])

@app.route('/guess', methods=['POST'])
def guess():
    user_choice = request.form['choice']
    correct_answer = request.form['answer']

    if user_choice == correct_answer:
        session['score'] += 1  # Increment score
        session['current_game'] = new_game(token)  # Start new game
        return render_template('game.html', game=session['current_game'], score=session['score'])
    else:
        highest_score = update_highest_score()
        return redirect(url_for('loss', score=session['score'], highest_score=highest_score))

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

    return render_template('loss.html', score=session['score'], username=username, highest_score=highest_score)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('score', None)
    session.pop('current_game', None)
    return redirect(url_for('index'))

def update_highest_score():
    user_id = session.get('user_id')
    if user_id is not None:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT highest_score FROM users WHERE id = ?', (user_id,))
        highest_score = cursor.fetchone()[0]

        if session['score'] > highest_score:
            cursor.execute('UPDATE users SET highest_score = ? WHERE id = ?', (session['score'], user_id))
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
