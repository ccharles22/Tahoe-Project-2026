# ON MACBOOK
# PostgreSQL installation via Homebrew
brew install postgresql  #installing the latest version 
brew services start postgresql@18
brew services list #see what as started 

psql postgres #initialise the database cluster 

# it is possible to stop postgresql 
#brew services stop
psql --version #to visualize that the psql version is the correct one

