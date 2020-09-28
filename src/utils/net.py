import socket


def tcp_is_open(host, port, timeout=None):
    """
    Returns True if a TCP port is open and listening, False otherwise.
    """
    try:
        conn_kwargs = {}
        if timeout:
            conn_kwargs['timeout'] = timeout
        conn = socket.create_connection((host, port), **conn_kwargs)
        conn.close()
        return True
    except socket.error:
        return False
