import express from 'express';
import { Firestore } from '@google-cloud/firestore';
import { OpenAI } from 'openai';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import bodyParser from 'body-parser';
import { v4 as uuidv4 } from 'uuid';

dotenv.config();

const app = express();
const port = process.env.PORT || 8080;
app.use(bodyParser.json());

const { db } = require('./firebase');
const categoriesCollection = db.collection('domain_categories');
const summariesCollection = db.collection('category_summaries');
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

const USAGE_LOG = path.join(process.cwd(), 'usage_log.json');
if (!fs.existsSync(USAGE_LOG)) fs.writeFileSync(USAGE_LOG, '{}');

function isValidDomain(domain) {
  return !!domain && /^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(domain);
}

app.post('/get-category-mapping', async (req, res) => {
  const domains = req.body.domains || [];
  const response = {};

  for (const domain of domains) {
    if (!domain || domain.trim() === '/') {
      response[domain] = 'Uncategorized';
      continue;
    }
    try {
      const doc = await categoriesCollection.doc(domain).get();
      if (doc.exists) {
        response[domain] = doc.data().category || 'Uncategorized';
      } else {
        const prompt = `Categorize the domain '${domain}' into one of the following categories: Social Media, Entertainment, Work/Productivity, Shopping, Education, News, Other. Respond with just the category.`;
        const completion = await openai.chat.completions.create({
          model: 'gpt-4',
          messages: [
            { role: 'system', content: 'You are a helpful classifier.' },
            { role: 'user', content: prompt }
          ],
          max_tokens: 10
        });

        let category = completion.choices[0].message.content.trim();
        if (!category) category = 'Uncategorized';
        await categoriesCollection.doc(domain).set({ category });
        response[domain] = category;
      }
    } catch (err) {
      console.error(`❌ Error processing domain ${domain}:`, err);
      response[domain] = 'Uncategorized';
    }
  }

  res.json(response);
});

app.post('/submit-category-summary', async (req, res) => {
  const { timestamp, categorySummary, userId } = req.body;
  if (!timestamp || !categorySummary || !userId)
    return res.status(400).json({ error: 'Missing required fields' });

  try {
    const parsedTime = new Date(timestamp);
    const day = parsedTime.toISOString().split('T')[0];

    await summariesCollection.doc(timestamp).set({
      timestamp,
      day,
      userId,
      summary: categorySummary
    });
    res.json({ status: 'success' });
  } catch (err) {
    res.status(400).json({ error: 'Invalid timestamp format', details: err.message });
  }
});

app.get('/get-summary-history', async (req, res) => {
  const { day, userId } = req.query;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) {
    return res.status(400).json({ error: 'Invalid date format. Use YYYY-MM-DD' });
  }

  try {
    let query = summariesCollection.where('day', '==', day);
    if (userId) query = query.where('userId', '==', userId);
    const snapshot = await query.get();

    const result = snapshot.docs.map(doc => {
      const data = doc.data();
      return {
        timestamp: data.timestamp,
        userId: data.userId,
        summary: data.summary
      };
    }).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    res.json(result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/track-usage', (req, res) => {
  const { userId, timestamp, usage } = req.body;
  if (!userId || !timestamp || !usage) return res.status(400).json({ error: 'Missing usage data' });

  const logs = JSON.parse(fs.readFileSync(USAGE_LOG, 'utf-8'));
  if (!logs[userId]) {
    logs[userId] = {
      totalCalls: 0,
      totalCost: 0,
      lastActive: null,
      id: uuidv4()
    };
  }

  logs[userId].totalCalls += usage.llmCall || 0;
  logs[userId].totalCost += usage.cost || 0;
  logs[userId].lastActive = new Date(timestamp).toISOString();

  fs.writeFileSync(USAGE_LOG, JSON.stringify(logs, null, 2));
  res.json({ status: 'success', userId });
});

app.get('/usage', (req, res) => {
  const logs = JSON.parse(fs.readFileSync(USAGE_LOG, 'utf-8'));
  res.json(logs);
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.listen(port, () => {
  console.log(`✅ Server listening on port ${port}`);
});
