from flask import Flask, render_template, url_for  
# render_template is used to render HTML templates
# url_for is used to build URLs for specific functions

# Initialize the Flask application
app = Flask(__name__)


# define the home route
@app.route('/')
def home():
    return render_template('home.html') # Render the home page template

@app.route('/login')
def login():
    return render_template('login.html') # Render the login page template

@app.route('/register')
def register():
    return render_template('register.html') # Render the register page template

#Start the web portal server

if __name__ == '__main__':
    app.run(debug=True)

