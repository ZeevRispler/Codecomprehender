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
pip install codecomprehender
```

Or install from source:

```bash
git clone https://github.com/yourusername/codecomprehender.git
cd codecomprehender
pip install -e .
```

## Quick Start

1. Get an OpenAI API key from https://platform.openai.com/
2. Set it as an environment variable:
   ```bash
   export OPENAI_API_KEY="your-key-here"
   ```
3. Run it on your Java project:
   ```bash
   codecomprehender /path/to/your/java/project
   ```

That's it! You'll get a new folder with `_commented` versions of all your Java files.

## Usage Examples

```bash
# Local Java project
codecomprehender ~/code/my-java-app

# GitHub repository
codecomprehender https://github.com/spring-projects/spring-boot

# Specify output directory
codecomprehender ~/code/my-app --output ~/Desktop/commented-code

# Use different AI model
codecomprehender ~/code/my-app --model gpt-4

# Skip diagram generation (faster)
codecomprehender ~/code/my-app --comments-only

# Only generate diagrams
codecomprehender ~/code/my-app --diagrams-only
```

## Requirements

- Python 3.8+
- OpenAI API key
- Git (for cloning repositories)
- Graphviz (optional, for architecture diagrams)

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

## How It Works

1. **Parses** your Java files to understand the structure
2. **Analyzes** classes, methods, and fields 
3. **Generates** contextual comments using AI
4. **Creates** new files with `_commented` suffix
5. **Preserves** your original code (never modifies it)

## Configuration

Create a `.env` file in your project:

```env
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4o-mini
```

Or pass options via command line:

```bash
codecomprehender ~/code/app --api-key your-key --model gpt-4
```

## Limitations

- Works best with clean, compilable Java code
- Some newer Java features (records, sealed classes) might be skipped
- Generated comments are AI-generated and should be reviewed
- Requires internet connection for OpenAI API calls

## Development

```bash
git clone https://github.com/yourusername/codecomprehender.git
cd codecomprehender
pip install -e ".[dev]"

# Run tests
python -m pytest

# Format code  
black src/
```

## Contributing

Pull requests welcome! Please:

1. Keep it simple - this tool should be easy to use
2. Add tests for new features
3. Update documentation
4. Follow the existing code style

## License

MIT License - see LICENSE file for details.

---

**Note:** This tool generates AI comments that should be reviewed before committing to production code. The quality depends on your code structure and the AI model used.