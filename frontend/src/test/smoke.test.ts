import { describe, it, expect } from 'vitest';

describe('test harness', () => {
  it('runs basic assertions', () => {
    expect(1 + 1).toBe(2);
  });

  it('has a jsdom document with jest-dom matchers', () => {
    document.body.innerHTML = '<button>hi</button>';
    expect(document.querySelector('button')).toBeInTheDocument();
  });
});
