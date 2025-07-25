# Excludarr

A command-line utility that helps you sync your Sonarr instance with streaming services, automatically unmonitoring or deleting TV shows and seasons from Sonarr when they become available on your configured streaming platforms.

## Features

- **Free Provider APIs**: Real-time streaming availability data from TMDB and other free provider APIs
- **TMDB Integration**: Primary data source using The Movie Database (TMDB) with completely free access
- **Multi-Provider Fallback**: Intelligent fallback system (TMDB → Streaming Availability → Utelly)
- **Enhanced Dry Run**: Detailed preview showing exactly which series/seasons would be affected
- **Intelligent Rate Limiting**: Respects API limits with exponential backoff and quota tracking
- **Automatic Sync**: Automatically detects when TV shows are available on your streaming services
- **Flexible Actions**: Choose to either unmonitor or delete series from Sonarr
- **Country-Specific**: Supports country-specific streaming providers across 180+ countries
- **Comprehensive Provider Support**: Extensive provider database with smart name mapping
- **Safety Features**: Excludes recently added series to prevent accidental removal
- **Rich CLI Interface**: Beautiful terminal output with tables and progress indicators
- **Robust Error Handling**: Comprehensive error recovery and retry logic with graceful fallbacks

## Installation

### Prerequisites

- Python 3.12 or higher
- uv package manager (recommended) or pip
- Access to a Sonarr instance
- TMDB API key (free from [themoviedb.org](https://www.themoviedb.org/settings/api))

### Using uv (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd excludarr

# Install dependencies
uv sync

# Install excludarr in development mode
uv pip install -e .

# Run excludarr
uv run excludarr --help
```

### Using pip

```bash
# Clone the repository
git clone <repository-url>
cd excludarr

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Run excludarr
excludarr --help
```

## Quick Start

### 1. Get TMDB API Key

1. Create a free account at [themoviedb.org](https://www.themoviedb.org/)
2. Go to Settings → API and generate an API key
3. Keep this key handy for configuration

### 2. Initialize Configuration

```bash
# Create example configuration file
uv run excludarr config init

# Validate your configuration
uv run excludarr config validate
```

### 3. Configure Your Settings

Edit the generated `excludarr.yml` file with your Sonarr, TMDB, and streaming provider details:

```yaml
sonarr:
  url: "http://localhost:8989"
  api_key: "your-sonarr-api-key"

provider_apis:
  tmdb:
    api_key: "your-tmdb-api-key"    # Required - completely free
    enabled: true
    rate_limit: 40                  # requests per 10 seconds
    cache_ttl: 86400               # 24 hours
  
  streaming_availability:
    enabled: false                  # Enable for enhanced fallback
    rapidapi_key: "your_key"       # 100 requests/day free
    daily_quota: 100
  
  utelly:
    enabled: false                  # Enable for price data
    rapidapi_key: "your_key"       # 1000 requests/month free
    monthly_quota: 1000

streaming_providers:
  - name: "netflix"
    country: "US"
  - name: "amazon-prime"
    country: "DE"
  - name: "disney-plus"
    country: "US"

sync:
  action: "unmonitor"  # or "delete"
  dry_run: true
  exclude_recent_days: 7
```

### 4. Test Connection

```bash
# Validate configuration and test connections
uv run excludarr config validate

# List available streaming providers
uv run excludarr providers list --popular
```

### 5. Run Sync

```bash
# Dry run to preview changes (shows detailed action table)
uv run excludarr sync --dry-run

# Apply changes (unmonitor series)
uv run excludarr sync --action unmonitor

# Apply changes (delete series) with confirmation
uv run excludarr sync --action delete
```

## Configuration

### Sonarr Settings

```yaml
sonarr:
  url: "http://localhost:8989"           # Your Sonarr URL
  api_key: "your-32-character-api-key"   # Sonarr API key
```

### Provider API Settings

#### TMDB (Primary - Required)

```yaml
provider_apis:
  tmdb:
    api_key: "your-tmdb-api-key"    # Get from themoviedb.org/settings/api
    enabled: true                   # Always keep enabled
    rate_limit: 40                  # Requests per 10 seconds (TMDB limit)
    cache_ttl: 86400               # 24 hours (recommended by TMDB)
```

#### Streaming Availability API (Optional Fallback)

```yaml
  streaming_availability:
    enabled: false                  # Enable when needed
    rapidapi_key: "your-rapidapi-key"  # From rapidapi.com
    daily_quota: 100               # Free tier limit
    cache_ttl: 43200              # 12 hours
```

#### Utelly API (Optional Fallback)

```yaml
  utelly:
    enabled: false                  # Enable when needed
    rapidapi_key: "your-rapidapi-key"  # From rapidapi.com
    monthly_quota: 1000            # Free tier limit
    cache_ttl: 604800             # 7 days
```

### Streaming Providers

```yaml
streaming_providers:
  - name: "netflix"        # Provider name (normalized automatically)
    country: "US"          # ISO country code
  - name: "amazon-prime"
    country: "DE"
  - name: "hulu"
    country: "US"
```

### Sync Settings

```yaml
sync:
  action: "unmonitor"              # Action: "unmonitor" or "delete"
  dry_run: true                    # Preview mode
  exclude_recent_days: 7           # Skip recently added series
```

## Commands

### Configuration Management

```bash
# Initialize configuration file
excludarr config init [--force]

# Validate configuration
excludarr config validate

# Show configuration info
excludarr config info
```

### Provider Management

```bash
# List all providers
excludarr providers list

# List providers by country
excludarr providers list --country US

# Search providers
excludarr providers list --search netflix

# Show popular providers
excludarr providers list --popular

# Show region-specific providers
excludarr providers list --region EU

# Get provider details
excludarr providers info netflix

# Show provider statistics
excludarr providers stats

# Validate provider/country combination
excludarr providers validate netflix US
```

### Sync Operations

```bash
# Dry run sync (preview only)
excludarr sync --dry-run

# Sync with specific action
excludarr sync --action unmonitor
excludarr sync --action delete

# Automated sync (skip confirmations)
excludarr sync --confirm

# Verbose output
excludarr -vvv sync

# JSON output for automation/scripting
excludarr sync --json
```

## JSON Output for Automation

Excludarr supports JSON output mode for integration with automation tools and scripts:

```bash
# JSON output with clean machine-readable format
excludarr sync --dry-run --json

# Example JSON structure:
{
  "timestamp": "2025-07-25T15:19:09.256952",
  "dry_run": true,
  "action": "unmonitor",
  "summary": {
    "total_processed": 139,
    "successful": 139,
    "failed": 0,
    "actions": {"none": 137, "unmonitor": 2},
    "providers": {"amazon-prime": 2}
  },
  "results": [
    {
      "series_id": 1208,
      "series_title": "Cross",
      "success": true,
      "action_taken": "unmonitor",
      "message": "Available on amazon-prime",
      "provider": "amazon-prime",
      "error": null
    }
  ]
}
```

**JSON Output Features:**
- Clean JSON format with no log messages mixed in
- Machine-readable timestamps and statistics
- Detailed per-series results with actions taken
- Error handling with structured error information
- Perfect for CI/CD pipelines and automation scripts

## API Providers

### TMDB (The Movie Database)

**Primary Provider - Completely Free**
- **Coverage**: 180+ countries worldwide
- **Rate Limit**: 40 requests per 10 seconds
- **Cost**: Completely free
- **Data**: Basic streaming availability (yes/no per provider)
- **Registration**: Free account at [themoviedb.org](https://www.themoviedb.org)

### Streaming Availability API (Optional)

**Secondary Provider - Free Tier Available**
- **Coverage**: Enhanced provider data
- **Rate Limit**: 100 requests per day (free tier)
- **Cost**: Free tier available
- **Data**: Enhanced availability information
- **Registration**: RapidAPI account required

### Utelly API (Optional)

**Tertiary Provider - Free Tier Available**
- **Coverage**: Price and platform information
- **Rate Limit**: 1000 requests per month (free tier)
- **Cost**: Free tier available
- **Data**: Price and availability data
- **Registration**: RapidAPI account required

## How It Works

1. **Series Discovery**: Excludarr retrieves all monitored series from your Sonarr instance
2. **TMDB Lookup**: Queries TMDB API for streaming availability data using IMDb IDs
3. **Provider Mapping**: Maps TMDB provider names to your configured streaming services
4. **Fallback Providers**: Optional fallback to other free APIs when TMDB data is unavailable
5. **Intelligent Caching**: TTL-based caching (24h for TMDB, variable for others)
6. **Rate Limiting**: Respects API limits with automatic backoff and retry
7. **Decision Making**: Determines actions based on season-level analysis with series-level fallback
8. **Action Execution**: Unmonitors or deletes series according to configuration
9. **Safety Measures**: Excludes recently added series and provides detailed logging

### Availability Logic

- **Complete Availability Requirement**: Series must be completely available on a streaming provider (all monitored seasons) to be unmonitored or deleted
- **Season-Level Analysis**: Analyzes availability at both series and season levels for intelligent decisions
- **All-or-Nothing Approach**: Only series with complete availability across all monitored seasons are processed
- **Smart Fallback**: When season data is unavailable, uses series-level availability as fallback
- **Monitored Season Focus**: Only considers monitored seasons when determining complete availability
- **Recently Added Exclusion**: Automatically excludes recently added series (configurable days)
- **Intelligent Normalization**: Provider names are automatically normalized for consistent matching

### Data Sources Priority

1. **TMDB**: Primary source, completely free, extensive coverage with Bearer token support
2. **Streaming Availability**: Fallback for enhanced data with deep links (100 req/day free)
3. **Utelly**: Fallback for price information (1000 req/month free)  
4. **Cache**: Intelligent SQLite-based caching with TTL to minimize API calls

### Enhanced Dry Run

Excludarr now shows detailed dry run output including:
- **Series names** that would be affected
- **Action type** (unmonitor/delete)  
- **Reason** (which provider has the content)
- **Provider** where content was found

Example dry run output:
```
Dry Run Actions:
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Series               ┃ Action          ┃ Reason               ┃ Provider     ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ Breaking Bad         │ Would Unmonitor │ Available on         │ netflix      │
│ The Office           │ Would Unmonitor │ Available on         │ amazon-prime │
└──────────────────────┴─────────────────┴──────────────────────┴──────────────┘
```

## Supported Streaming Providers

Excludarr automatically maps provider names from TMDB and other APIs. Common providers include:

**Global Providers:**
- Netflix
- Amazon Prime Video
- Disney Plus
- Apple TV Plus
- Paramount Plus
- HBO Max

**Regional Providers:**
- Hulu (US)
- BBC iPlayer (UK)
- ARD (Germany)
- Canal Plus (France)
- And many more...

Provider names are automatically normalized (e.g., "Amazon Prime Video" → "amazon-prime").

## Development

### Project Structure

```
excludarr/
   excludarr/           # Main package
      cli.py          # Command-line interface
      config.py       # Configuration management
      sonarr.py       # Sonarr API client
      tmdb_client.py  # TMDB API client
      providers.py    # Provider management
      sync.py         # Core sync logic
      availability.py # Availability checking
      models.py       # Data models
      logging.py      # Logging setup
   tests/              # Test suite
   excludarr/data/     # Provider database
   .agent-os/          # Agent OS documentation
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_tmdb_client.py

# Run with coverage
uv run pytest --cov=excludarr

# Verbose output
uv run pytest -v

# Generate HTML coverage report
uv run pytest --cov=excludarr --cov-report=html
```

### Test Coverage

Current test coverage: **86%** with comprehensive test suite including 31 CLI integration tests

**Core Modules Coverage:**
- TMDB Client: **97%** - Primary API integration  
- Streaming Availability Client: **94%** - Secondary API fallback
- Utelly Client: **94%** - Tertiary API fallback
- Simple Cache: **94%** - Caching system
- Models: **97%** - Configuration validation
- CLI Interface: **82%** - Comprehensive command testing
- Sync Engine: **86%** - Core sync logic
- Provider Manager: **79%** - Multi-provider coordination
- Providers: **99%** - Provider database management
- Config: **100%** - Configuration management
- Sonarr Client: **70%** - Sonarr API integration

**Test Suite Features:**
- 31 CLI integration tests covering all commands and options
- Comprehensive mocking for external API calls
- Error handling and edge case coverage
- Configuration validation testing

The core functionality has excellent test coverage, with the main API clients (TMDB, Streaming Availability, Utelly) and caching systems achieving >90% coverage. The CLI interface now has comprehensive test coverage with 31 tests covering all command functionality.

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `uv run pytest`
6. Submit a pull request

## Logging

Excludarr uses structured logging with multiple verbosity levels:

```bash
# Basic logging
excludarr sync

# Verbose logging
excludarr -v sync

# Debug logging
excludarr -vv sync

# Trace logging (maximum detail)
excludarr -vvv sync
```

Logs include:
- API interactions and rate limiting
- Series processing decisions
- Provider mapping and normalization
- Error details and recovery

## Safety Features

- **Dry Run Mode**: Preview all changes before applying
- **Recent Series Exclusion**: Skip recently added series (configurable)
- **Confirmation Prompts**: User confirmation for destructive operations
- **Comprehensive Validation**: Configuration and provider validation
- **Rate Limiting**: Automatic API rate limit compliance
- **Error Recovery**: Retry logic for transient failures
- **Detailed Logging**: Full audit trail of all operations

## Troubleshooting

### Common Issues

**Configuration Validation Errors:**
```bash
# Check configuration syntax
excludarr config validate

# Verify Sonarr connectivity
excludarr sync --dry-run
```

**TMDB API Issues:**
```bash
# Verify TMDB API key is correct
excludarr config validate

# Check rate limiting
excludarr -vv sync
```

**Provider Issues:**
```bash
# Verify provider exists
excludarr providers info netflix

# Check country availability
excludarr providers validate netflix US
```

**API Connection Issues:**
- Verify Sonarr URL is accessible
- Check API key is correct (32 characters)
- Ensure TMDB API key is valid
- Check internet connectivity for API calls

### Getting Help

1. Check configuration with `excludarr config validate`
2. Run in dry-run mode first: `excludarr sync --dry-run`
3. Use verbose logging: `excludarr -vvv sync`
4. Check the logs for detailed error messages
5. Verify TMDB API key at [themoviedb.org](https://www.themoviedb.org/settings/api)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with [Click](https://click.palletsprojects.com/) for CLI interface
- Uses [pyarr](https://github.com/totaldebug/pyarr) for Sonarr API integration
- Utilizes [Rich](https://github.com/Textualize/rich) for beautiful terminal output
- Powered by [Pydantic](https://pydantic.dev/) for configuration validation
- Streaming data from [TMDB](https://www.themoviedb.org/) and other free APIs
- HTTP client powered by [httpx](https://www.python-httpx.org/) for async operations