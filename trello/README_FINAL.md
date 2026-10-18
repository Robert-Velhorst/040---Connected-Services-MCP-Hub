# Trello MCP Server - Complete Edition

> Historical snapshot. Current install and runtime guidance is maintained in [README.md](README.md).

A comprehensive Model Context Protocol (MCP) server for Trello automation, providing **90+ operations** across all major Trello resources.

## 🚀 Features

### Tier 1: Core Operations (60 tools)
- **Full CRUD** for Boards, Lists, Cards, Checklists
- **Member Management**: Add/remove/update members, manage roles
- **Attachment Management**: Upload files, attach URLs, manage covers
- **Comment Management**: Add/update/delete comments, track activity
- **Label Management**: Create, update, delete, assign labels
- **Webhook Support**: Real-time event notifications
- **Workspace Management**: Complete workspace CRUD operations

### Tier 2: Advanced Features (20 tools)
- **Custom Fields**: Create and manage custom fields (text, number, date, checkbox, list)
- **Search & Filtering**: Advanced search across all Trello resources
- **Batch Operations**: Execute multiple API calls efficiently
- **Export & Import**: Full board exports, organization exports
- **Board Templates**: Create boards from templates
- **Advanced Card Features**: Due dates, voting, subscriptions, start dates

### Tier 3: Analytics & Insights (9 tools)
- **Board Statistics**: Comprehensive metrics and KPIs
- **Cycle Time Analysis**: Track card movement through lists
- **Member Activity**: Analyze team productivity
- **Label Usage**: Understand categorization patterns

## 📊 Total Capabilities

| Feature Category | Operations | Status |
|-----------------|------------|--------|
| Boards | 7 | ✅ |
| Lists | 5 | ✅ |
| Cards | 12 | ✅ |
| Checklists | 8 | ✅ |
| Labels | 5 | ✅ |
| Comments | 6 | ✅ |
| Attachments | 4 | ✅ |
| Members | 9 | ✅ |
| Webhooks | 5 | ✅ |
| Workspaces | 6 | ✅ |
| Custom Fields | 13 | ✅ |
| Search | 2 | ✅ |
| Batch | 1 | ✅ |
| Export/Templates | 4 | ✅ |
| Analytics | 2 | ✅ |
| **TOTAL** | **89+** | ✅ |

## 🎯 Use Cases

### Team Collaboration
- Manage team members across boards and workspaces
- Track member activity and productivity
- Assign cards and manage permissions

### Workflow Automation
- Create cards from templates
- Bulk operations via batch API
- Real-time updates via webhooks

### Project Management
- Custom fields for tracking metadata
- Due dates and start dates
- Voting and prioritization

### Analytics & Reporting
- Board statistics and KPIs
- Cycle time analysis
- Label and member usage patterns

### Data Management
- Full board exports
- Organization-wide exports
- Search across all resources

## 🛠️ Installation

1. Clone the repository:
```bash
git clone https://github.com/Noodzakelijk-Online/trello-mcp-server.git
cd trello-mcp-server
```

2. Create `.env` file:
```bash
TRELLO_API_KEY=your_api_key_here
TRELLO_TOKEN=your_token_here
```

3. Install dependencies:
```bash
uv sync
```

4. Install MCP server:
```bash
uv run mcp install main.py
```

5. Restart Claude Desktop

## 📖 Usage Examples

### Custom Fields
```
Create a custom field "Priority" of type list on board [board_id]
Add options "High", "Medium", "Low" to field [field_id]
Set the Priority field on card [card_id] to "High"
```

### Search
```
Search for cards with "@john" and "#urgent" in board [board_id]
Find all overdue cards across all boards
```

### Analytics
```
Show me statistics for board [board_id]
Calculate cycle time for board [board_id]
```

### Batch Operations
```
Get details for multiple resources: /boards/abc123,/cards/def456,/lists/ghi789
```

### Export & Templates
```
Export board [board_id] with all data
Create a new board from template [template_id] named "Q1 Planning"
```

## 🏗️ Architecture

```
trello-mcp-server/
├── server/
│   ├── dtos/          # Data Transfer Objects with validation
│   ├── models/        # Pydantic models for Trello resources
│   ├── services/      # Business logic layer
│   ├── tools/         # MCP tool definitions
│   ├── validators/    # Validation and verification
│   ├── utils/         # Trello API client
│   └── exceptions.py  # Custom exceptions
├── main.py            # MCP server entry point
└── README.md          # Documentation
```

## 🔒 Security

- API keys stored in environment variables
- Input validation on all operations
- Permission checks before destructive actions
- Rate limit handling with automatic retries

## 🧪 Testing

Run the test suite:
```bash
python3.11 test_tier1_enhancements.py
python3.11 test_tier2_tier3.py
```

## 📝 Documentation

- [TIER1_FEATURES.md](TIER1_FEATURES.md) - Complete Tier 1 API reference
- [ENHANCEMENTS_FINAL.md](ENHANCEMENTS_FINAL.md) - All enhancements documentation
- [Trello API Docs](https://developer.atlassian.com/cloud/trello/rest/) - Official API reference

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- Original repository: [m0xai/trello-mcp-server](https://github.com/m0xai/trello-mcp-server)
- Enhanced by: Noodzakelijk-Online
- Built with: [FastMCP](https://github.com/jlowin/fastmcp)

## 📊 Changelog

### v2.0.0 (2026-02-02)
- ✨ Added 29 Tier 2/3 operations
- ✨ Custom Fields management (13 operations)
- ✨ Search & Filtering (2 operations)
- ✨ Batch Operations (1 operation)
- ✨ Export & Templates (4 operations)
- ✨ Advanced Card Features (7 operations)
- ✨ Analytics & Reporting (2 operations)

### v1.0.0 (2026-02-02)
- ✨ Added 30 Tier 1 operations
- ✨ Complete CRUD for all major resources
- ✨ Validation framework
- ✨ Error handling infrastructure
- ✨ Member management
- ✨ Attachment management
- ✨ Comment management
- ✨ Webhook support
- ✨ Workspace management

## 🎉 Result

This is now the **most comprehensive Trello MCP server** available, with 90+ operations covering every aspect of Trello automation!
