import os
from flask import Flask, request, jsonify, g, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from exa_py import Exa
from openai import OpenAI
from pymongo import MongoClient

app = Flask(__name__)
MONGO_URI = os.environ.get('MONGO_URI')
mongo = MongoClient(MONGO_URI)

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data['username']
    password = data['password']
    
    db = mongo.db  # Access the database directly
    if db.users.find_one({'username': username}):
        return jsonify({'error': 'User already exists'}), 400

    hashed_password = generate_password_hash(password)
    db.users.insert_one({'username': username, 'password': hashed_password})

    return jsonify({'message': 'User created successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']

    db = mongo.db  # Access the database directly
    user = db.users.find_one({'username': username})

    if user and check_password_hash(user['password'], password):
        session['username'] = username  # Set session variable upon successful login
        return jsonify({'message': 'Login successful'}), 200

    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    openai_api_key = data.get('OPENAI_API_KEY')
    exa_api_key = data.get('EXA_API_KEY')
    questions = data.get('questions')
    username = session.get('username') or data.get('username')

    if not all([openai_api_key, exa_api_key, questions]):
        return jsonify({'error': 'Missing parameters'}), 400

    exa = Exa(exa_api_key)
    openai_client = OpenAI(api_key=openai_api_key)

    highlights_options = {
        "num_sentences": 7,
        "highlights_per_url": 1,
    }

    info_for_llm = []
    for question in questions:
        search_response = exa.search_and_contents(question, highlights=highlights_options, num_results=3, use_autoprompt=True)
        info = [sr.highlights[0] for sr in search_response.results]
        info_for_llm.append(info)

    responses = []
    for question, info in zip(questions, info_for_llm):
        system_prompt = "You are RAG researcher. Read the provided contexts and, if relevant, use them to answer the user's question."
        user_prompt = f"Sources: {info}\n\nQuestion: {question}"

        completion = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        response_content = completion.choices[0].message.content
        response = {
            "question": question,
            "answer": response_content
        }
        responses.append(response)

        if username:
            mongo.db.chats.insert_one({'username': username, 'question': question, 'answer': response_content})

    return jsonify(responses)

@app.route('/test_db')
def test_db():
    # Test database connection and count online users
    db = mongo.db  # Access the database directly
    online_users = db.users.find({'online': True})
    online_count = online_users.count()  # Count the number of online users
    
    return f'Connected to MongoDB, found {online_count} online users.'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
