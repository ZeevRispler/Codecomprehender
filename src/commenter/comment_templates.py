"""Templates for common comment patterns"""

CLASS_TEMPLATE = """/**
 * {description}
 * 
 * @author CodeComprehender
 * @see {related_classes}
 */"""

METHOD_TEMPLATE = """/**
 * {description}
 * 
{params}
{return_doc}
{throws_doc}
 */"""

FIELD_TEMPLATE = "// {description}"

FILE_TEMPLATE = """/**
 * {description}
 * 
 * Package: {package}
 * @author CodeComprehender
 */"""