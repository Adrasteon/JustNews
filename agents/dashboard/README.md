---
title: JustNews Public Dashboard Agent
description: Auto-generated description for JustNews Public Dashboard Agent
tags: [documentation]
status: current
last_updated: 2025-10-18
---

# JustNews Public Dashboard Agent

The Public Dashboard Agent serves the JustNews public-facing website and API endpoints, providing access to AI-analyzed news articles, credibility scores, and research data.

## Features

- **Public Website**: Modern, responsive website displaying AI-analyzed news
- **REST API**: Comprehensive API for articles, analysis data, and statistics
- **Real-time Data**: Live updates from the JustNews analysis pipeline
- **Research APIs**: Specialized endpoints for academic and journalistic research
- **Credibility Scoring**: Transparent source credibility and fact-checking data

## Quick Start

### Starting the Dashboard

```bash
# From project root
./agents/dashboard/start_dashboard.sh

# Or manually
cd agents/dashboard
python3 main.py --host 0.0.0.0 --port 8014
```

The dashboard will be available at:
- **Website**: http://localhost:8014
- **API Docs**: http://localhost:8014/api/docs
- **Health Check**: http://localhost:8014/health

### Testing

```bash
# Run the test suite
python3 agents/dashboard/test_public_api.py
```

## API Endpoints

### Public Endpoints

#### Statistics
- `GET /api/public/stats` - System statistics and metrics

#### Articles
- `GET /api/public/articles` - Get filtered and paginated articles
- `GET /api/public/article/{article_id}` - Get detailed article information

#### Analysis Data
- `GET /api/public/trending-topics` - Current trending topics
- `GET /api/public/source-credibility` - Source credibility rankings
- `GET /api/public/fact-checks` - Recent fact check corrections
- `GET /api/public/temporal-analysis` - Temporal trend analysis

#### Search & Export
- `GET /api/public/search/suggestions` - Search suggestions
- `GET /api/public/export/articles` - Export articles for research

#### Research APIs
- `GET /api/public/research/metrics` - Detailed research metrics

### Query Parameters

#### Article Filtering
```javascript
GET /api/public/articles?page=1&limit=20&search=AI&topic=technology&source=reuters&credibility_min=80&credibility_max=100&sentiment=positive&date_from=2024-01-01&date_to=2024-12-31&sort=newest
```

#### Temporal Analysis
```javascript
GET /api/public/temporal-analysis?topic=climate&date_from=2024-01-01&date_to=2024-12-31&interval=day
```

## Website Features

### Main Pages
- **Home** (`/`): Latest news with AI analysis overlays
- **Article View** (`/article/{id}`): Detailed article with full analysis
- **Search** (`/search?q=query`): Search results and filtering
- **About** (`/about`): Information about JustNews and methodology
- **API Docs** (`/api-docs`): Interactive API documentation

### Analysis Features
- **Credibility Scores**: Source reliability ratings (0-100)
- **Fact Check Status**: Verification confidence levels
- **Sentiment Analysis**: Positive/negative/neutral scoring
- **Bias Detection**: Political and sensationalism indicators
- **Topic Classification**: Automated topic tagging
- **Readability Metrics**: Flesch scores and grade levels

## Data Models

### Article Object
```json
{
  "id": "article-001",
  "title": "AI Revolutionizes Healthcare",
  "content": "Full article text...",
  "summary": "AI systems detect cancer with 99% accuracy...",
  "source": "Medical Journal",
  "source_credibility": 92,
  "source_reliability": "high",
  "url": "https://example.com/article-001",
  "published_date": "2024-01-15T10:30:00Z",
  "sentiment_score": 0.3,
  "fact_check_score": 95,
  "bias_score": 0.1,
  "emotional_tone": "Optimistic",
  "readability_score": "College",
  "topics": ["Healthcare", "AI", "Medical Technology"],
  "comment_count": 47,
  "word_count": 850,
  "reading_time": 4
}
```

### Source Credibility
```json
{
  "name": "Reuters",
  "score": 95,
  "articles": 1250,
  "reliability": "high"
}
```

## Research API Access

For academic and research use, contact the JustNews team for API key access. Research endpoints provide:

- **Bulk Data Export**: Large-scale article datasets
- **Temporal Analysis**: Trend analysis over time periods
- **Advanced Filtering**: Complex query capabilities
- **Raw Analysis Data**: Unprocessed AI analysis results
- **Usage Analytics**: API usage statistics

### Example Research Query
```javascript
GET /api/public/research/metrics?date_from=2024-01-01&date_to=2024-12-31&granularity=day
```

## Configuration

### Environment Variables
- `DASHBOARD_PORT`: Port to run the dashboard (default: 8014)
- `HOST`: Host to bind to (default: 0.0.0.0)
- `MCP_BUS_URL`: MCP bus URL (default: http://localhost:8000)

### Files
- `public_website.html`: Main website template
- `public_api.py`: API endpoint implementations
- `requirements.txt`: Python dependencies
- `config.json`: Dashboard configuration

## Development

### Project Structure
```
agents/dashboard/
├── main.py              # FastAPI application
├── public_api.py        # Public API endpoints
├── public_website.html  # Website template
├── test_public_api.py   # API test suite
├── start_dashboard.sh   # Startup script
├── requirements.txt     # Dependencies
├── static/             # Static assets
└── config.json         # Configuration
```

### Adding New Endpoints

1. Add endpoint to `public_api.py`
2. Include router in `main.py`
3. Update API documentation
4. Add tests to `test_public_api.py`

### Website Customization

The website uses Bootstrap 5 and Chart.js. Modify `public_website.html` to customize the UI.

## Monitoring

### Health Checks
- `GET /health`: Basic health status
- `GET /ready`: Readiness for traffic

### Metrics
- Request/response metrics via JustNewsMetrics
- GPU monitoring integration
- API usage statistics

## Security

### Public Access
- CORS enabled for web access
- Rate limiting on API endpoints
- Input validation on all parameters

### Research Access
- API key authentication for research endpoints
- Usage monitoring and quotas
- Data export restrictions

## Troubleshooting

### Common Issues

**Dashboard won't start**
- Check port 8014 is available
- Verify Python dependencies: `pip install -r requirements.txt`
- Check MCP bus connectivity

**API returns errors**
- Verify MCP bus is running on port 8000
- Check agent health: `GET /get_status`
- Review logs for specific error messages

**Website not loading**
- Ensure `public_website.html` exists
- Check static file serving
- Verify CORS configuration

### Logs
Dashboard logs are available through the standard JustNews logging system. Check the console output or log files for detailed error information.

## Contributing

1. Follow the existing code patterns in `public_api.py`
2. Add comprehensive error handling
3. Include input validation
4. Update tests for new functionality
5. Document API changes

## License

This component is part of the JustNews system. See project LICENSE for details.
