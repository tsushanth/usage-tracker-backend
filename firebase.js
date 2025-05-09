const admin = require('firebase-admin');
const path = require('path');
const { getFirestore } = require('firebase-admin/firestore');

const firebaseConfig = require(path.join(__dirname, 'secrets', 'serviceAccountKeyFirebase.json'));

// Initialize Firebase
const firebase_app = admin.initializeApp({
  credential: admin.credential.cert(firebaseConfig),
  databaseURL: "https://usage-tracker-f5251.firebaseio.com",
  appId: "1:401121533183:web:d4794690fe2832e30500ca"
});

const db = getFirestore(firebase_app);
db.settings({ ignoreUndefinedProperties: true });
console.log('Firebase initialized successfully!');

module.exports = { db };