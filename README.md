# CodeComprehender

Add AI-generated comments to Java code automatically. Uses OpenAI to create helpful JavaDoc comments and inline explanations.

## What It Does

Takes messy, undocumented Java code and adds useful comments:

```java
// Before
public class UserService {
    private UserRepository repo;
    
    public User findById(Long id) {
        return repo.findById(id);
    }
}

// After  
/**
 * Service class for managing user operations and data access.
 * Handles business logic for user-related functionality.
 */
public class UserService {
    private UserRepository repo;  // Repository for user data persistence
    
    /**
     * Retrieves a user by their unique identifier.
     * 
     * @param id the unique user ID to search for
     * @return User object if found, null otherwise
     */
    public User findById(Long id) {
        return repo.findById(id);
    }
}
```

## Installation

```bash
git clone https://github.com/yourusername/codecomprehender.git
cd codecomprehender
pip install -r requirements.txt
```

## Quick Start

1. Get an OpenAI API key from https://platform.openai.com/
2. Set it as an environment variable:
   ```bash
   export OPENAI_API_KEY="your-key-here"
   ```
3. Run it on a GitHub repository:
   ```bash
   python -m src.main https://github.com/user/repo --output ./output
   ```

That's it! You'll get a new folder with `_commented` versions of all your Java files plus architecture diagrams.

## Usage

```bash
# Basic usage - analyze a GitHub repo
python -m src.main https://github.com/spring-projects/spring-boot --output ./spring-commented

# Use a different AI model (default is gpt-4o-mini)
python -m src.main https://github.com/user/repo --output ./output --model gpt-4
```

## Options

```bash
python -m src.main <GITHUB_URL> --output <OUTPUT_DIR> [--model <MODEL>]

Required:
  GITHUB_URL           GitHub repository URL (https://github.com/user/repo)
  --output DIR         Where to save the commented code and diagrams

Optional:
  --model MODEL        OpenAI model to use (default: gpt-4o-mini)
                       Options: gpt-4o-mini, gpt-4, gpt-3.5-turbo
```

## Requirements

- Python 3.8+
- OpenAI API key
- Git (for cloning repositories)
- Graphviz (for architecture diagrams)

### Installing Graphviz

**Mac:**
```bash
brew install graphviz
```

**Ubuntu/Debian:**
```bash
sudo apt-get install graphviz
```

**Windows:**
Download from https://graphviz.org/download/

## Configuration

Create a `.env` file in the project directory:

```env
OPENAI_API_KEY=your-key-here
```

Or set it as an environment variable:
```bash
export OPENAI_API_KEY="your-key-here"
```

## What You Get

After running the tool, your output directory will contain:

```
output/
├── src/                          # Commented Java files
│   └── main/java/.../*_commented.java
└── diagrams/                     # Architecture diagrams
    ├── project_overview.png
    ├── class_diagram.png
    ├── dependency_graph.png
    └── architecture_report.md
```

## How It Works

1. **Clones** the GitHub repository
2. **Analyzes** all Java files in parallel
3. **Generates** contextual comments using AI
4. **Creates** `_commented.java` versions of all files
5. **Generates** architecture diagrams and analysis
6. **Preserves** original code structure

## Performance Features

- **Multiprocessing**: Uses multiple CPU cores for speed
- **Async API calls**: Generates multiple comments concurrently
- **Smart filtering**: Skips test files and generated code automatically
- **Progress tracking**: Shows real-time progress on large codebases

## Limitations

- Only works with GitHub repositories (public or private with access)
- Some newer Java features (records, sealed classes) might be skipped
- Generated comments should be reviewed before production use
- Requires internet connection for OpenAI API calls
- API costs scale with codebase size

---

**Note:** This tool generates AI comments that should be reviewed before committing to production code.