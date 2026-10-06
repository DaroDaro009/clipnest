// The Python desktop window replaces HTTP requests with a local Qt WebChannel.
if (typeof qt !== 'undefined' && typeof QWebChannel !== 'undefined') {
  const desktopReady = new Promise(resolve => {
    new QWebChannel(qt.webChannelTransport, channel => resolve(channel.objects.clipnest));
  });
  window.clipnestDesktop = async (path, options = {}) => {
    const bridge = await desktopReady;
    const result = await new Promise(resolve => bridge.request(path, options.method || 'GET', options.body || '', resolve));
    const data = JSON.parse(result);
    if (data.error) throw new Error(data.error);
    return data;
  };
}
