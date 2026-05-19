import unittest

from competitor_agents.web_research import DuckDuckGoParser, PageTextParser, normalize_duckduckgo_url


class WebResearchTest(unittest.TestCase):
    def test_duckduckgo_parser_extracts_results(self):
        html = """
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fpricing">Example Pricing</a>
        <a class="result__snippet">Example has AI pricing and product features.</a>
        """
        parser = DuckDuckGoParser()
        parser.feed(html)

        self.assertEqual(len(parser.results), 1)
        self.assertEqual(parser.results[0].title, "Example Pricing")
        self.assertEqual(parser.results[0].url, "https://example.com/pricing")
        self.assertIn("AI pricing", parser.results[0].snippet)

    def test_page_parser_ignores_scripts_and_extracts_body(self):
        html = """
        <html>
          <head><title>Product Page</title><script>ignored ignored ignored ignored</script></head>
          <body>
            <p>This product offers AI search, team notes, project documentation, and pricing for paid plans.</p>
          </body>
        </html>
        """
        parser = PageTextParser()
        parser.feed(html)

        self.assertEqual(" ".join(parser.title_parts).strip(), "Product Page")
        self.assertIn("AI search", " ".join(parser.text_parts))
        self.assertNotIn("ignored", " ".join(parser.text_parts))

    def test_normalize_duckduckgo_redirect(self):
        url = "/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs"
        self.assertEqual(normalize_duckduckgo_url(url), "https://example.com/docs")


if __name__ == "__main__":
    unittest.main()
