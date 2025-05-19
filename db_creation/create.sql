CREATE TABLE Customer (
    id SERIAL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE Restaurant (
    id SERIAL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(15) NOT NULL,
    menu BYTEA,
    building INT NOT NULL,
        street VARCHAR(255) NOT NULL,
        zipcode VARCHAR(10) NOT NULL,
    hygiene_rating INT NOT NULL,
    inspection_date DATE NOT NULL,
    borough INT NOT NULL,
    cuisine_description VARCHAR(255) NOT NULL,
    violation_description TEXT NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE Moderator (
    id SERIAL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE DMs (
    id SERIAL,
    sender_id INT NOT NULL,
    receiver_id INT NOT NULL,
    message BYTEA NOT NULL,
    flagged BOOLEAN DEFAULT FALSE,
    flagged_by INT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES Customer(id),
    FOREIGN KEY (receiver_id) REFERENCES Customer(id),
    FOREIGN KEY (flagged_by) REFERENCES Moderator(id),
    CONSTRAINT chk_dm_sender_receiver CHECK (sender_id <> receiver_id), -- prevent sending DMs to self
    PRIMARY KEY (id)
);

CREATE TABLE Comments (
    id SERIAL,
    commenter_id INT NOT NULL,
    restaurant_id INT NOT NULL,
    comment BYTEA,
    karma INT DEFAULT 0,
    flagged BOOLEAN DEFAULT FALSE,
    flagged_by INT,
    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (commenter_id) REFERENCES Customer(id),
    FOREIGN KEY (restaurant_id) REFERENCES Restaurant(id),
    FOREIGN KEY (flagged_by) REFERENCES Moderator(id),
    PRIMARY KEY (id)
);

CREATE TABLE Replies (
    id SERIAL,
    commenter_id INT NOT NULL,
    comment_id INT NOT NULL,
    comment BYTEA,
    karma INT DEFAULT 0,
    flagged BOOLEAN DEFAULT FALSE,
    flagged_by INT,
    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (commenter_id) REFERENCES Customer(id),
    FOREIGN KEY (comment_id) REFERENCES Comments(id),
    FOREIGN KEY (flagged_by) REFERENCES Moderator(id),
    PRIMARY KEY (id)
);

CREATE TABLE Favorite_Restaurants (
    customer_id INT NOT NULL,
    restaurant_id INT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES Customer(id),
    FOREIGN KEY (restaurant_id) REFERENCES Restaurant(id),
    PRIMARY KEY (customer_id, restaurant_id)
);

-- psql -h database-clean-bites.c3ayoouusmcp.us-east-2.rds.amazonaws.com -p 5432 -U cleanbites -d postgres
