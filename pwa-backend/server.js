const express = require('express');
const jwt = require('jsonwebtoken');
const cors = require('cors');
const path = require('path');

const app = express();
app.use(express.json());
app.use(cors());
app.use(express.static(path.join(__dirname, 'public')));

const SPREADSHEET_ID = process.env.SPREADSHEET_ID;
const SHEET_NAME     = process.env.SHEET_NAME || 'CONTROL GASTOS 2026';
const PIN            = process.env.PWA_PIN    || '1234';

const MES_COLS    = { ENE:3, FEB:4, MAR:5, ABR:6, MAY:7, JUN:8, JUL:9, AGO:10, SEP:11, OCT:12, NOV:13, DIC:14 };
const MES_NOMBRES = ['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC'];

const FILAS_VARIABLES = {
  'comida/supermercado':37,'comida':37,'supermercado':37,
  'restaurantes':38,'restaurante':38,
  'gasolina':39,
  'salud/farmacia':40,'salud':40,'farmacia':40,
  'ropa':41,
  'ocio/entretenimiento':42,'ocio':42,
  'otros':43,
};

async function getAccessToken() {
  const creds = JSON.parse(process.env.GOOGLE_CREDENTIALS_JSON);
  const privateKey = creds.private_key.replace(/\\n/g, '\n');
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iss: creds.client_email,
    scope: 'https://www.googleapis.com/auth/spreadsheets',
    aud: 'https://oauth2.googleapis.com/token',
    exp: now + 3600,
    iat: now,
  };
  const token = jwt.sign(payload, privateKey, { algorithm: 'RS256' });
  const resp = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${token}`,
  });
  const data = await resp.json();
  return data.access_token;
}

async function sheetsRequest(range, method = 'GET', body = null) {
  const token = await getAccessToken();
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${process.env.SPREADSHEET_ID}/values/${encodeURIComponent(range)}`;
  const opts = { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  return r.json();
}

async function sheetsBatchGet(ranges) {
  const token = await getAccessToken();
  const qs = ranges.map(r => `ranges=${encodeURIComponent(r)}`).join('&');
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${process.env.SPREADSHEET_ID}/values:batchGet?${qs}`;
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  return r.json();
}

async function sheetsUpdate(range, values) {
  const token = await getAccessToken();
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${process.env.SPREADSHEET_ID}/values/${encodeURIComponent(range)}?valueInputOption=USER_ENTERED`;
  const r = await fetch(url, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  });
  return r.json();
}

function cellToFloat(val) {
  if (!val || val === '-' || val === '') return 0;
  return parseFloat(String(val).replace(/\./g,'').replace(',','.').replace(/[^0-9.\-]/g,'')) || 0;
}
function floatToCell(n) {
  return n.toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2}) + ' €';
}
function mesActual() { return MES_NOMBRES[new Date().getMonth()]; }
function colLetra(i) { return String.fromCharCode(65+i); }
function rangoA1(fila,colIdx) { return `${SHEET_NAME}!${colLetra(colIdx)}${fila}`; }

app.post('/api/auth', (req,res) => {
  req.body.pin === PIN ? res.json({ok:true}) : res.status(401).json({ok:false,error:'PIN incorrecto'});
});

app.get('/api/dashboard', async (req,res) => {
  try {
    const mes = req.query.mes || mesActual();
    const colIdx = MES_COLS[mes];
    if (!colIdx) return res.status(400).json({error:'Mes inválido'});
    const col = colLetra(colIdx);
    const data = await sheetsBatchGet([
      `${SHEET_NAME}!${col}49`,`${SHEET_NAME}!${col}50`,`${SHEET_NAME}!${col}51`,
      `${SHEET_NAME}!${col}52`,`${SHEET_NAME}!${col}53`,`${SHEET_NAME}!B37:${col}43`,
    ]);
    const v = data.valueRanges;
    const get = i => v[i]?.values?.[0]?.[0] || '0';
    const variables = (v[5]?.values||[]).map(row=>({nombre:row[0]||'',importe:cellToFloat(row[row.length-1])})).filter(r=>r.nombre&&r.importe>0);
    res.json({ mes, ingresos:cellToFloat(get(0)), gastosFijos:cellToFloat(get(1)), gastosRecurrentes:cellToFloat(get(2)), gastosVariables:cellToFloat(get(3)), ahorro:cellToFloat(get(4)), variables });
  } catch(err) { console.error(err); res.status(500).json({error:err.message}); }
});

app.get('/api/anual', async (req,res) => {
  try {
    const data = await sheetsBatchGet(
      ['D49:O49','D50:O50','D51:O51','D52:O52','D53:O53'].map(r=>`${SHEET_NAME}!${r}`)
    );
    const rows = data.valueRanges.map(r=>r.values?.[0]||[]);
    const meses = MES_NOMBRES.map((m,i)=>({
      mes:m, ingresos:cellToFloat(rows[0][i]), fijos:cellToFloat(rows[1][i]),
      recurrentes:cellToFloat(rows[2][i]), variables:cellToFloat(rows[3][i]),
      ahorro:cellToFloat(rows[4][i]),
      totalGasto:cellToFloat(rows[1][i])+cellToFloat(rows[2][i])+cellToFloat(rows[3][i]),
    }));
    res.json({meses});
  } catch(err) { console.error(err); res.status(500).json({error:err.message}); }
});

app.post('/api/gasto', async (req,res) => {
  try {
    const {categoria,importe,mes:mesParam} = req.body;
    if (!categoria||!importe) return res.status(400).json({error:'Faltan datos'});
    const mes = (mesParam||mesActual()).toUpperCase();
    const colIdx = MES_COLS[mes];
    if (!colIdx) return res.status(400).json({error:'Mes inválido'});
    const fila = FILAS_VARIABLES[categoria.toLowerCase().trim()];
    if (!fila) return res.status(400).json({error:`Categoría desconocida: ${categoria}`});
    const rango = rangoA1(fila, colIdx);
    const r = await sheetsRequest(rango);
    const anterior = cellToFloat(r.values?.[0]?.[0]);
    const nuevo = anterior + parseFloat(importe);
    await sheetsUpdate(rango, [[floatToCell(nuevo)]]);
    res.json({ok:true,categoria,mes,anterior,nuevo,mensaje:`✅ ${importe}€ añadidos a ${categoria} (${mes}). Total: ${nuevo.toFixed(2)}€`});
  } catch(err) { console.error(err); res.status(500).json({error:err.message}); }
});

app.get('/api/categorias', (_,res) => res.json({categorias:[
  {key:'comida/supermercado',label:'Comida / Supermercado',emoji:'🛒'},
  {key:'restaurante',label:'Restaurantes',emoji:'🍽️'},
  {key:'gasolina',label:'Gasolina',emoji:'⛽'},
  {key:'salud',label:'Salud / Farmacia',emoji:'💊'},
  {key:'ropa',label:'Ropa',emoji:'👕'},
  {key:'ocio',label:'Ocio / Entretenimiento',emoji:'🎭'},
  {key:'otros',label:'Otros',emoji:'📦'},
]}));

app.get('*', (_,res) => res.sendFile(path.join(__dirname,'public','index.html')));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`✅ PWA backend en puerto ${PORT}`));
