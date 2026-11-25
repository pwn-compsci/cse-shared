// AITA_PROJECT_ROUTES: same-origin bridge on the existing code-server service.
exports.router.use('/exam_api/tutor', express.json({limit:'8kb'}), (req, res) => {
  const http = require('http');
  const body = req.method === 'POST' ? JSON.stringify(req.body || {}) : null;
  const headers = {'Content-Type':'application/json'};
  if (body) headers['Content-Length'] = Buffer.byteLength(body);
  if (typeof req.headers['x-tutor-token'] === 'string') headers['X-Tutor-Token'] = req.headers['x-tutor-token'];
  const upstream = http.request({hostname:'127.0.0.1',port:5001,
    path:'/exam_api/tutor' + req.url,method:req.method,headers}, response => {
      res.statusCode = response.statusCode;
      for (const name of ['content-type','cache-control','retry-after']) {
        if (response.headers[name]) res.setHeader(name,response.headers[name]);
      }
      response.pipe(res);
  });
  upstream.setTimeout(90000, () => upstream.destroy());
  upstream.on('error', () => {
    if (!res.headersSent) res.status(503).json({error:'Aita is unavailable; please try again shortly.'});
    else res.end();
  });
  req.on('aborted', () => upstream.destroy());
  upstream.end(body);
});
