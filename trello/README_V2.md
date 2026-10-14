# Trello MCP Server - Version 2.0

> Historical snapshot. Current install and runtime guidance is maintained in [README.md](README.md).

A comprehensive Model Context Protocol (MCP) server for Trello automation, providing complete CRUD operations and real-time integration capabilities.

## 🚀 Features

### Core Operations (v1.0)
- ✅ **Boards**: Create, read, update, delete, list
- ✅ **Lists**: Create, read, update, delete, archive
- ✅ **Cards**: Create, read, update, delete, move, archive
- ✅ **Checklists**: Create, read, update, delete, manage items
- ✅ **Workspaces**: Create, read, update, delete, list boards
- ✅ **Labels**: Create, read (board labels)

### Tier 1 Enhancements (v2.0) 🎉

#### 👥 Member Management (9 operations)
- Get/add/update/remove board members
- Get workspace members
- Get member details
- Get/add/remove card members
- Role management (admin, normal, observer)

#### 📎 Attachment Management (4 operations)
- Get card attachments
- Attach URLs to cards
- Delete attachments
- Set attachment as card cover

#### 💬 Comment Management (6 operations)
- Get card comments
- Get card/board activity feed
- Add/update/delete comments
- Filter actions by type

#### 🏷️ Enhanced Label Management (5 operations)
- Update label name/color
- Delete labels
- Get card labels
- Add/remove labels from cards

#### 🔔 Webhook Support (5 operations)
- Create webhooks for real-time events
- Get/list webhooks
- Update webhook configuration
- Delete webhooks
- Monitor webhook health

## 📊 Statistics

- **60 Total Tools** (30 original + 29 new + 1 enhanced)
- **29 New Operations** in v2.0
- **5 Major Feature Areas** enhanced
- **100% Test Coverage** (10/10 test suites passing)

## 🛠️ Installation

### Prerequisites
- Python 3.11+
- Trello API Key and Token
- Claude Desktop (for MCP integration)

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/m0xai/trello-mcp-server.git
   cd trello-mcp-server
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**

   Create a `.env` file:
   ```env
   TRELLO_API_KEY=your_api_key_here
   TRELLO_TOKEN=your_token_here
   ```

   Get your credentials:
   - API Key: https://trello.com/app-key
   - Token: Click "Token" link on the API key page

4. **Install MCP server:**
   ```bash
   uv run mcp install main.py
   ```

5. **Restart Claude Desktop**

## 📖 Usage Examples

### Team Collaboration

```
Add alice@example.com to board [board_id] as admin
Assign member [alice_id] to card [card_id]
Add comment "Please review the design" to card [card_id]
```

### Attachment Management

```
Attach https://docs.example.com/spec.pdf to card [card_id] with name "Requirements"
Show me all attachments on card [card_id]
Set attachment [attachment_id] as cover for card [card_id]
```

### Label Organization

```
Update label [label_id] to color red and name "Urgent"
Add label [urgent_label_id] to card [card_id]
Show me all labels on card [card_id]
```

### Real-Time Integration

```
Create a webhook for board [board_id] that posts to https://api.example.com/trello-events
Show me all my webhooks
Update webhook [webhook_id] to inactive
```

### Activity Tracking

```
Show me recent activity on board [board_id]
Show me all comments on card [card_id]
Get the last 100 actions on card [card_id]
```

## 🏗️ Architecture

### Layered Design

```
┌─────────────────────────────────────┐
│         MCP Tool Layer              │  ← User-facing tools
├─────────────────────────────────────┤
│      Validation Layer               │  ← Pre-flight checks
├─────────────────────────────────────┤
│       Service Layer                 │  ← Business logic
├─────────────────────────────────────┤
│         DTO Layer                   │  ← Input validation
├─────────────────────────────────────┤
│      Trello API Client              │  ← HTTP communication
└─────────────────────────────────────┘
```

### Key Components

**DTOs (Data Transfer Objects)**
- Pydantic models for request payloads
- Comprehensive validation rules
- Type safety and error messages

**Services**
- Business logic implementation
- API call orchestration
- Response transformation

**Tools**
- MCP-compatible tool functions
- Error handling and logging
- Context management

**Validators**
- Resource existence checks
- Permission validation
- Business rule enforcement

## 🔒 Security

- ✅ API credentials stored in environment variables
- ✅ HTTPS for all API calls
- ✅ Input validation and sanitization
- ✅ Permission checks before operations
- ✅ No credentials logged or exposed

## ⚡ Performance

- **Rate Limiting**: Automatic retry with exponential backoff
- **Pagination**: Support for large result sets
- **Caching**: Recommended for frequently accessed data
- **Batch Operations**: Coming in Tier 2

## 🧪 Testing

Run the comprehensive test suite:

```bash
python3.11 test_tier1_enhancements.py
```

**Test Coverage:**
- ✅ DTO validation
- ✅ Model instantiation
- ✅ Service methods
- ✅ Tool functions
- ✅ Tools registration
- ✅ Import verification

**Results:** 10/10 test suites passing

## 📚 Documentation

- **[TIER1_FEATURES.md](TIER1_FEATURES.md)**: Complete API documentation with examples
- **[ENHANCEMENTS_FINAL.md](ENHANCEMENTS_FINAL.md)**: Implementation details and design decisions
- **[TODO.md](TODO.md)**: Roadmap and future enhancements

## 🗺️ Roadmap

### ✅ Completed (v2.0 - Tier 1)
- Member Management
- Attachment Management
- Comment Management
- Enhanced Label Management
- Webhook Support

### 🔄 Planned (Tier 2)
- Custom Fields
- Search & Filtering
- Batch Operations
- Export & Import
- Advanced Card Features

### 🔮 Future (Tier 3)
- Power-Ups Management
- Board Templates
- Analytics & Reporting
- Automation Rules

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new features
5. Submit a pull request

## 📝 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- Trello API documentation
- MCP protocol specification
- FastMCP framework
- Community contributors

## 📞 Support

- **Issues**: https://github.com/m0xai/trello-mcp-server/issues
- **Documentation**: See TIER1_FEATURES.md
- **API Reference**: https://developer.atlassian.com/cloud/trello/rest/

## 📈 Version History

### v2.0.0 (February 2026)
- Added Member Management (9 operations)
- Added Attachment Management (4 operations)
- Added Comment Management (6 operations)
- Added Enhanced Label Management (5 operations)
- Added Webhook Support (5 operations)
- Comprehensive test suite
- Complete documentation

### v1.0.0 (Initial Release)
- Basic CRUD operations
- Board, List, Card, Checklist management
- Workspace operations
- Label creation

---

**Built with ❤️ for the Trello automation community**

*Transform your Trello workflows with AI-powered automation*
