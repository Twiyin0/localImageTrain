const http = require('http');
const { Readable } = require('stream');
const { pipeline } = require('stream/promises');
const fs = require('fs');
const path = require('path');

const PORT = Number(process.env.PORT || process.env.WEBUI_PORT || 7861);
const BACKEND_BASE = new URL(process.env.WD_TAGGER_API_URL || 'http://wd-tagger-api:8000');
const BACKEND_API_KEY = (process.env.WD_TAGGER_API_KEY || '').trim();
const REQUEST_TIMEOUT_MS = Number(process.env.WD_TAGGER_WEBUI_TIMEOUT_MS || 600000);
const PUBLIC_DIR = path.join(__dirname, 'public');

const MIME_TYPES = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8',
  '.ico': 'image/x-icon',
};

function sendJson(res, statusCode, payload) {
  const body = Buffer.from(JSON.stringify(payload, null, 2));
  res.writeHead(statusCode, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': body.length,
    'cache-control': 'no-store',
  });
  res.end(body);
}

function sendText(res, statusCode, body, contentType = 'text/plain; charset=utf-8') {
  const buffer = Buffer.isBuffer(body) ? body : Buffer.from(String(body));
  res.writeHead(statusCode, {
    'content-type': contentType,
    'content-length': buffer.length,
    'cache-control': 'no-store',
  });
  res.end(buffer);
}

function isApiRequest(urlPath) {
  return urlPath === '/api' || urlPath.startsWith('/api/');
}

function staticPath(urlPath) {
  if (urlPath === '/' || urlPath === '') {
    return path.join(PUBLIC_DIR, 'index.html');
  }
  const relative = urlPath.replace(/^\/+/, '');
  const resolved = path.normalize(path.join(PUBLIC_DIR, relative));
  const pathFromPublic = path.relative(PUBLIC_DIR, resolved);
  if (pathFromPublic.startsWith('..') || path.isAbsolute(pathFromPublic)) {
    return null;
  }
  return resolved;
}

function getContentType(filePath) {
  return MIME_TYPES[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

function createProxyHeaders(req, hasBody) {
  const headers = new Headers();
  const blockedHeaders = new Set([
    'connection',
    'content-length',
    'host',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailer',
    'transfer-encoding',
    'upgrade',
  ]);
  for (const [key, value] of Object.entries(req.headers)) {
    if (value == null) continue;
    const lower = key.toLowerCase();
    if (blockedHeaders.has(lower)) continue;
    headers.set(key, Array.isArray(value) ? value.join(',') : value);
  }
  if (BACKEND_API_KEY) {
    headers.set('x-api-key', BACKEND_API_KEY);
  }
  if (hasBody && !headers.has('content-type') && req.headers['content-type']) {
    headers.set('content-type', req.headers['content-type']);
  }
  return headers;
}

async function proxyRequest(req, res, targetPath) {
  const incomingUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const backendUrl = new URL(targetPath + incomingUrl.search, BACKEND_BASE);
  const hasBody = !['GET', 'HEAD'].includes(req.method || 'GET');
  const headers = createProxyHeaders(req, hasBody);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  timeout.unref();

  try {
    const upstream = await fetch(backendUrl, {
      method: req.method,
      headers,
      body: hasBody ? req : undefined,
      duplex: hasBody ? 'half' : undefined,
      signal: controller.signal,
    });

    const responseHeaders = {};
    upstream.headers.forEach((value, key) => {
      if (key.toLowerCase() === 'content-length') return;
      responseHeaders[key] = value;
    });

    res.writeHead(upstream.status, responseHeaders);
    if (!upstream.body) {
      res.end();
      return;
    }
    await pipeline(Readable.fromWeb(upstream.body), res);
  } catch (error) {
    sendJson(res, 502, {
      error: 'Backend request failed',
      detail: error instanceof Error ? error.message : String(error),
    });
  } finally {
    clearTimeout(timeout);
  }
}

function serveStatic(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const filePath = staticPath(url.pathname);
  if (!filePath) {
    sendText(res, 403, 'Forbidden');
    return;
  }

  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
    const fallback = path.join(PUBLIC_DIR, 'index.html');
    res.writeHead(200, {
      'content-type': 'text/html; charset=utf-8',
      'cache-control': 'no-store',
    });
    fs.createReadStream(fallback).pipe(res);
    return;
  }

  res.writeHead(200, {
    'content-type': getContentType(filePath),
    'cache-control': 'no-store',
  });
  fs.createReadStream(filePath).pipe(res);
}

const server = http.createServer((req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('X-Frame-Options', 'DENY');

  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (req.method === 'GET' && url.pathname === '/health') {
    sendJson(res, 200, {
      status: 'ok',
      frontend: 'node-static',
      backend: BACKEND_BASE.toString(),
      auth_proxy: Boolean(BACKEND_API_KEY),
    });
    return;
  }

  if (isApiRequest(url.pathname)) {
    const targetPath = url.pathname === '/api' ? '/' : url.pathname.slice(4);
    proxyRequest(req, res, targetPath || '/');
    return;
  }

  if (req.method === 'GET' || req.method === 'HEAD') {
    serveStatic(req, res);
    return;
  }

  sendText(res, 405, 'Method Not Allowed');
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`WD Tagger webui listening on http://0.0.0.0:${PORT}`);
});
