import uasyncio as asyncio


class Response:

    def __init__(self, f):
        self.raw = f
        self.encoding = "utf-8"
        self._cached = None

    async def aclose(self):
        if self.raw:
            await self.raw.aclose()
            self.raw = None
        self._cached = None

    async def content(self):
        if self._cached is None:
            self._cached = await self.raw.read()
            await self.raw.aclose()
            self.raw = None
        return self._cached

    async def text(self):
        return str(await self.content(), self.encoding)

    async def json(self):
        import ujson
        return ujson.loads(await self.content())


async def request(method, url, data=None, json=None, headers={}, stream=None):
    try:
        proto, dummy, host, path = url.split("/", 3)
    except ValueError:
        proto, dummy, host = url.split("/", 2)
        path = ""
    if proto == "http:":
        port = 80
    elif proto == "https:":
        # import ussl
        port = 443
    else:
        raise ValueError("Unsupported protocol: " + proto)

    if ":" in host:
        host, port = host.split(":", 1)
        port = int(port)

    reader, writer = await asyncio.open_connection(host, port)
    await writer.awrite(b"%s /%s HTTP/1.0\r\n" % (method, path))
    if "Host" not in headers:
        await writer.awrite(b"Host: %s\r\n" % host)
    # Iterate over keys to avoid tuple alloc
    for k in headers:
        await writer.awrite(k)
        await writer.awrite(b": ")
        await writer.awrite(headers[k])
        await writer.awrite(b"\r\n")
    if json is not None:
        assert data is None
        import ujson
        data = ujson.dumps(json)
    if data:
        await writer.awrite(b"Content-Length: %d\r\n" % len(data))
    await writer.awrite(b"\r\n")
    if data:
        await writer.awrite(data)

    l = await reader.readline()
    protover, status, msg = l.split(None, 2)
    status = int(status)
    # print(protover, status, msg)
    while True:
        l = await reader.readline()
        if not l or l == b"\r\n":
            break
        # print(l)
        if l.startswith(b"Transfer-Encoding:"):
            if b"chunked" in l:
                raise ValueError("Unsupported " + l)
        elif l.startswith(b"Location:") and not 200 <= status <= 299:
            raise NotImplementedError("Redirects not yet supported")

    resp = Response(reader)
    resp.status_code = status
    resp.reason = msg.rstrip()
    return resp


async def head(url, **kw):
    return await request("HEAD", url, **kw)


async def get(url, **kw):
    return await request("GET", url, **kw)


async def post(url, **kw):
    return await request("POST", url, **kw)


async def put(url, **kw):
    return await request("PUT", url, **kw)


async def patch(url, **kw):
    return await request("PATCH", url, **kw)


async def delete(url, **kw):
    return await request("DELETE", url, **kw)
