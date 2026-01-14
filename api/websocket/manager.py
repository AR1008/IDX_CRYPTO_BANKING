"""
WebSocket Manager - Simplified
Purpose: Real-time notifications
"""

from flask_socketio import SocketIO, emit
from flask import request
import jwt

from config.settings import settings
from core.events.event_manager import EventManager


class WebSocketManager:
    """Manages WebSocket connections"""
    
    def __init__(self, socketio: SocketIO):
        self.socketio = socketio
        self.users = {}  # {user_idx: [sid1, sid2, ...]} - Support multiple connections
        
        # Subscribe to events
        EventManager.subscribe('transaction_completed', self.on_tx_complete)
        EventManager.subscribe('block_mined', self.on_block_mined)
        EventManager.subscribe('consensus', self.on_consensus)
        
        print("✅ WebSocket manager ready")
    
    def on_tx_complete(self, data: dict):
        """Transaction completed - notify users"""
        print(f"📨 TX Complete event: {data.get('tx_hash', '')[:16]}...")
        
        sender = data.get('sender_idx')
        receiver = data.get('receiver_idx')
        
        # Notify sender
        if sender in self.users:
            for sid in self.users[sender]:
                self.socketio.emit('tx_complete', {
                    'type': 'sent',
                    'hash': data.get('tx_hash', '')[:16] + '...',
                    'amount': str(data.get('amount'))
                }, to=sid)
                print(f"  → Sent to {sender[:16]}... (sid: {sid})")
        
        # Notify receiver
        if receiver in self.users and receiver != sender:
            for sid in self.users[receiver]:
                self.socketio.emit('tx_complete', {
                    'type': 'received',
                    'hash': data.get('tx_hash', '')[:16] + '...',
                    'amount': str(data.get('amount'))
                }, to=sid)
                print(f"  → Sent to {receiver[:16]}... (sid: {sid})")
    
    def on_block_mined(self, data: dict):
        """Block mined - broadcast to all"""
        print(f"📨 Block mined event: #{data.get('block_index')}")
        
        # Broadcast to everyone
        all_sids = [sid for sids in self.users.values() for sid in sids]
        for sid in all_sids:
            self.socketio.emit('block_mined', {
                'block': data.get('block_index'),
                'txs': data.get('transactions_count')
            }, to=sid)
        
        print(f"  → Broadcast to {len(all_sids)} connections")
    
    def on_consensus(self, data: dict):
        """Consensus achieved - broadcast to all"""
        print(f"📨 Consensus event: #{data.get('block_index')}")
        
        # Broadcast to everyone
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
            token = auth_data.get('token')
            if not token:
                print("❌ No token provided")
                return False
            
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
            user_idx = payload['user_idx']
            sid = request.sid
            
            # Add to users dict (support multiple connections)
            if user_idx not in self.users:
                self.users[user_idx] = []
            self.users[user_idx].append(sid)
            
            print(f"✅ Connected: {user_idx[:16]}... (sid: {sid}, total: {len(self.users[user_idx])} connections)")
            
            # Send confirmation
            emit('connected', {'user': user_idx[:16] + '...', 'sid': sid})
            
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {str(e)}")
            return False
    
    def disconnect(self):
        """Handle disconnection"""
        sid = request.sid
        
        # Find and remove this sid
        for user_idx, sids in list(self.users.items()):
            if sid in sids:
                sids.remove(sid)
                print(f"🔌 Disconnected: {user_idx[:16]}... (sid: {sid}, remaining: {len(sids)})")
                
                # Remove user if no more connections
                if not sids:
                    del self.users[user_idx]
                    print(f"  → User fully disconnected")
                break


# Global instance
manager = None


def init_websocket(app):
    """Initialize WebSocket"""
    global manager
    
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
    manager = WebSocketManager(socketio)
    
    @socketio.on('connect')
    def on_connect(auth):
        return manager.connect(auth)
    
    @socketio.on('disconnect')
    def on_disconnect():
        manager.disconnect()
    
    return socketio