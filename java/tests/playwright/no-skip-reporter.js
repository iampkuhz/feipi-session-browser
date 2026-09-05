class NoSkipReporter {
  constructor() {
    this.skipped = [];
  }

  onTestEnd(test, result) {
    if (result.status === 'skipped') {
      this.skipped.push(test.titlePath().join(' > '));
    }
  }

  async onEnd(result) {
    if (this.skipped.length === 0) {
      return undefined;
    }
    console.error(`[no-skip-reporter] ${this.skipped.length} Playwright tests were skipped:`);
    for (const title of this.skipped) {
      console.error(` - ${title}`);
    }
    return { status: 'failed' };
  }
}

module.exports = NoSkipReporter;
