# CodeComprehender

An intelligent tool designed to analyze and annotate Java codebases with meaningful comments using OpenAI, helping teams quickly understand complex, undocumented code.

## Features

- **Automated Code Commenting** – Generate contextual comments explaining functions, classes, and logic within the codebase using OpenAI's GPT models
- **Non-Intrusive Workflow** – Creates a duplicate of each file with appended comments (`*_commented.java`), ensuring the original code remains untouched
- **GitHub Integration** – Clone and analyze repositories directly from GitHub URLs
- **Architecture Visualization** – Generate package diagrams, class diagrams, and dependency graphs
- **Comprehensive Analysis** – Identify patterns, dependencies, and potential circular dependencies
- **Customizable** – Configure comment styles, diagram formats, and processing options

## Installation

### Prerequisites

- Python 3.8 or higher
- Git (for cloning repositories)
- Graphviz (for generating diagrams)
- OpenAI API key

### Install Graphviz

**Ubuntu/Debian:**
```bash
sudo apt-get install graphviz
```

**macOS:**
```bash
brew install graphviz
```

**Windows:**
Download and install from [Graphviz website](https://graphviz.org/download/)

### Install CodeComprehender

```bash
# Clone the repository
git clone https://github.com/yourusername/codecomprehender.git
cd codecomprehender

# Install dependencies
pip install -r requirements.txt

# Or install as a package
pip install -e .

# Create and configure .env file
cp .env.example .env
# Edit .env with your OpenAI API key
```

## Configuration

### Setting up API Keys

1. **Create a `.env` file** in the project root:
```bash
cp .env.example .env
```

2. **Edit the `.env` file** with your OpenAI credentials:
```env
OPENAI_API_KEY=your-openai-api-key-here

# Optional: For Azure OpenAI or custom endpoints
OPENAI_BASE_URL=https://your-custom-endpoint.openai.azure.com/
```

3. **Alternative methods**:
   - Set environment variables directly:
     ```bash
     export OPENAI_API_KEY="your-api-key-here"
     export OPENAI_BASE_URL="https://your-custom-endpoint.com/"  # Optional
     ```
   
   - Pass as command-line arguments:
     ```bash
     python -m codecomprehender /path/to/project --api-key "your-key" --base-url "your-url"
     ```

The priority order for API key configuration is:
1. Command-line arguments (`--api-key`, `--base-url`)
2. `.env` file in the project root
3. System environment variables

## Usage

### Basic Usage

Analyze a local Java project:
```bash
python -m codecomprehender /path/to/java/project
```

Analyze a GitHub repository:
```bash
python -m codecomprehender https://github.com/username/repo
```

### Command-Line Options

```bash
python -m codecomprehender [SOURCE] [OPTIONS]

Arguments:
  SOURCE  Local path or GitHub repository URL

Options:
  -o, --output-dir PATH     Output directory for processed files
  --api-key TEXT           OpenAI API key (overrides .env file)
  --base-url TEXT          OpenAI base URL (overrides .env file)
  -c, --config PATH        Configuration file path
  --comments-only          Generate only comments, skip architecture diagrams
  --architecture-only      Generate only architecture diagrams, skip comments
  -v, --verbose           Enable verbose logging
  --help                  Show this message and exit
```

### Examples

```bash
# Analyze with custom output directory
python -m codecomprehender https://github.com/spring-projects/spring-boot -o ./analyzed_output

# Generate only architecture diagrams
python -m codecomprehender /path/to/project --architecture-only

# Use custom configuration
python -m codecomprehender /path/to/project -c custom_config.yaml
```

## Configuration File

Create a `config.yaml` file to customize behavior:

```yaml
# OpenAI settings
openai_model: "gpt-4"
temperature: 0.3
max_tokens: 1000

# Comment generation settings
comment_style: "javadoc"
include_inline_comments: true
include_method_comments: true
include_class_comments: true

# Architecture settings
diagram_format: "png"  # or "svg", "pdf"
include_private_members: false
max_depth: 3

# File handling settings
file_suffix: "_commented"
ignore_patterns:
  - "*Test.java"
  - "*Generated.java"
  - "*.tmp"
encoding: "utf-8"
```

## Output Structure

```
output_directory/
├── src/                          # Commented Java files
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   ├── App_commented.java
│                   └── Service_commented.java
├── architecture/                 # Generated diagrams
│   ├── package_structure.png
│   ├── class_diagram.png
│   ├── dependency_graph.png
│   └── statistics_report.md
```

## Project Structure

```
codecomprehender/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── parser/                 # Java parsing logic
│   ├── commenter/              # AI comment generation
│   ├── architecture/           # Diagram generation
│   ├── utils/                  # Utilities
│   └── models/                 # Data models
├── tests/                      # Unit tests
├── config/                     # Configuration files
├── requirements.txt
├── setup.py
└── README.md
```

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Adding New Features

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Troubleshooting

### Common Issues

1. **OpenAI API Key Error**
   - Ensure your API key is set correctly
   - Check API key permissions and quotas

2. **Graphviz Not Found**
   - Ensure Graphviz is installed and in PATH
   - Try `dot -V` to verify installation

3. **Java Parse Errors**
   - Ensure the code is valid Java
   - Check for unsupported Java features

4. **Memory Issues with Large Projects**
   - Process packages separately
   - Increase Python heap size
   - Use `--architecture-only` or `--comments-only`

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## Acknowledgments

- Uses `javalang` for Java parsing
- Powered by OpenAI's GPT models
- Visualization with Graphviz

---

# Project Initialization Script (init_project.sh)
#!/bin/bash

# Create project structure
mkdir -p codecomprehender/src/{parser,commenter,architecture,utils,models}
mkdir -p codecomprehender/{tests,config}

# Create __init__.py files
touch codecomprehender/src/__init__.py
touch codecomprehender/src/parser/__init__.py
touch codecomprehender/src/commenter/__init__.py
touch codecomprehender/src/architecture/__init__.py
touch codecomprehender/src/utils/__init__.py
touch codecomprehender/src/models/__init__.py
touch codecomprehender/tests/__init__.py

# Create main entry point
cat > codecomprehender/src/__main__.py << 'EOF'
#!/usr/bin/env python3
from .main import main

if __name__ == '__main__':
    main()
EOF

chmod +x codecomprehender/src/__main__.py

echo "Project structure created successfully!"
echo "Next steps:"
echo "1. Copy the code files to their respective locations"
echo "2. Create .env file: cp .env.example .env"
echo "3. Edit .env and add your OpenAI API key"
echo "4. Install dependencies: pip install -r requirements.txt"
echo "5. Run: python -m codecomprehender https://github.com/user/repo"