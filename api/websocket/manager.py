# [DOC] WebSocket Manager — real-time event delivery to browser/app clients.
# [DOC] Flask-SocketIO keeps a persistent TCP connection open so the server can PUSH data without polling.
# [DOC] Clients authenticate with their JWT on connect; the manager maps IDX → socket session IDs.

"""
WebSocket Manager - Simplified
Purpose: Real-time notifications
"""

# [DOC] SocketIO is the server; emit() sends a named event to a specific socket session.
from flask_socketio import SocketIO, emit
# [DOC] Flask's request object in SocketIO context gives us request.sid (socket session ID).
from flask import request
# [DOC] PyJWT: decode the JWT that the client sends on WebSocket connect.
import jwt

# [DOC] settings.JWT_SECRET_KEY is needed to verify the client's token during WebSocket handshake.
from config.settings import settings
# [DOC] EventManager is an in-process pub/sub bus; services emit events, this class subscribes to them.
from core.events.event_manager import EventManager


class WebSocketManager:
    """Manages WebSocket connections"""

    def __init__(self, socketio: SocketIO):
        # [DOC] Store the SocketIO server reference so we can call socketio.emit() from event handlers.
        self.socketio = socketio
        # [DOC] users dict maps each IDX to a list of socket session IDs.
        # [DOC] One IDX can have multiple tabs/devices connected simultaneously.
        self.users = {}  # {user_idx: [sid1, sid2, ...]} - Support multiple connections

        # [DOC] Subscribe to internal events: when a service emits 'transaction_completed', call on_tx_complete.
        EventManager.subscribe('transaction_completed', self.on_tx_complete)
        EventManager.subscribe('block_mined', self.on_block_mined)
        EventManager.subscribe('consensus', self.on_consensus)

        print("✅ WebSocket manager ready")

    def on_tx_complete(self, data: dict):
        """Transaction completed - notify users"""
        print(f"📨 TX Complete event: {data.get('tx_hash', '')[:16]}...")

        # [DOC] Extract both parties from the event payload.
        sender = data.get('sender_idx')
        receiver = data.get('receiver_idx')

        # [DOC] For each socket session the sender has open, push a 'tx_complete' event.
        # [DOC] 'to=sid' targets one specific connection rather than broadcasting to all clients.
        if sender in self.users:
            for sid in self.users[sender]:
                self.socketio.emit('tx_complete', {
                    'type': 'sent',                          # [DOC] 'sent' tells the client's UI to show a debit.
                    'hash': data.get('tx_hash', '')[:16] + '...',  # [DOC] Truncated hash — enough for display, not full data.
                    'amount': str(data.get('amount'))
                }, to=sid)
                print(f"  → Sent to {sender[:16]}... (sid: {sid})")

        # [DOC] If receiver is different from sender, also notify the receiver (credit notification).
        if receiver in self.users and receiver != sender:
            for sid in self.users[receiver]:
                self.socketio.emit('tx_complete', {
                    'type': 'received',   # [DOC] 'received' tells the client's UI to show a credit.
                    'hash': data.get('tx_hash', '')[:16] + '...',
                    'amount': str(data.get('amount'))
                }, to=sid)
                print(f"  → Sent to {receiver[:16]}... (sid: {sid})")

    def on_block_mined(self, data: dict):
        """Block mined - broadcast to all"""
        print(f"📨 Block mined event: #{data.get('block_index')}")

        # [DOC] Flatten all per-user SID lists into a single list of every connected socket.
        all_sids = [sid for sids in self.users.values() for sid in sids]
        # [DOC] Broadcasting block events to everyone lets any UI update its blockchain explorer view.
        for sid in all_sids:
            self.socketio.emit('block_mined', {
                'block': data.get('block_index'),
                'txs': data.get('transactions_count')
            }, to=sid)

        print(f"  → Broadcast to {len(all_sids)} connections")

    def on_consensus(self, data: dict):
        """Consensus achieved - broadcast to all"""
        print(f"📨 Consensus event: #{data.get('block_index')}")

        # [DOC] Same broadcast pattern as block_mined — consensus is a system-wide event.
        all_sids = [sid for sids in self.users.values() for sid in sids]
        for sid in all_sids:
            self.socketio.emit('consensus', {
                'block': data.get('block_index'),
                'votes': data.get('votes')
            }, to=sid)

        print(f"  → Broadcast to {len(all_sids)} connections")

    def connect(self, auth_data: dict):
        """Handle new connection"""
        try:
            # [DOC] The client must pass {'token': '<jwt>'} as the auth object on connect.
            token = auth_data.get('token')
            if not token:
                print("❌ No token provided")
                return False  # [DOC] Returning False from the connect handler rejects the WebSocket handshake.

            # [DOC] Decode the JWT to extract the user's IDX — same secret key used in auth.py.
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
            user_idx = payload['user_idx']
            # [DOC] request.sid is the unique session ID assigned by SocketIO to this socket connection.
            sid = request.sid

            # [DOC] Initialise the SID list for this IDX if this is the user's first connection.
            if user_idx not in self.users:
                self.users[user_idx] = []
            # [DOC] Append (not replace) so existing tabs aren't evicted when a new tab connects.
            self.users[user_idx].append(sid)

            print(f"✅ Connected: {user_idx[:16]}... (sid: {sid}, total: {len(self.users[user_idx])} connections)")

            # [DOC] Confirm the connection back to the client so it knows it's authenticated.
            emit('connected', {'user': user_idx[:16] + '...', 'sid': sid})

            return True

        except Exception as e:
            print(f"❌ Connection failed: {str(e)}")
            return False  # [DOC] Any exception (expired token, bad token) rejects the connection.

    def disconnect(self):
        """Handle disconnection"""
        # [DOC] request.sid holds the SID of the socket that just disconnected.
        sid = request.sid

        # [DOC] Scan every user's SID list; remove the disconnecting SID.
        # [DOC] list() wraps the items() view so we can safely delete keys while iterating.
        for user_idx, sids in list(self.users.items()):
            if sid in sids:
                sids.remove(sid)
                print(f"🔌 Disconnected: {user_idx[:16]}... (sid: {sid}, remaining: {len(sids)})")

                # [DOC] If this was the user's last open connection, remove them from the dict entirely.
                if not sids:
                    del self.users[user_idx]
                    print(f"  → User fully disconnected")
                break


# [DOC] Module-level singleton; routes and services that need to send WebSocket events import this.
manager = None


def init_websocket(app):
    """Initialize WebSocket"""
    global manager

    # [DOC] Create the SocketIO server attached to the Flask app.
    # [DOC] cors_allowed_origins="*" lets any browser origin connect (lock this down in production).
    # [DOC] async_mode='threading' uses Python threads instead of gevent/asyncio (simpler for our use case).
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    # [DOC] Instantiate our manager, which registers event subscriptions with EventManager.
    manager = WebSocketManager(socketio)

    # [DOC] Register SocketIO event handlers — these are called by the SocketIO server, not HTTP routes.
    @socketio.on('connect')
    def on_connect(auth):
        # [DOC] 'auth' is the dict the client passes as the second argument to socket.connect({token}).
        return manager.connect(auth)

    @socketio.on('disconnect')
    def on_disconnect():
        manager.disconnect()

    return socketio
