from app import create_app # Import the create_app function to initialize the Flask application

app = create_app() # Create an instance of the Flask application using the factory function

# Run the Flask application in debug mode when this script is executed directly
if __name__ == '__main__':
    app.run(debug=True)

