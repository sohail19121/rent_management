import type { User } from './auth';

// The formatters need the company currency outside React components.
let currentUser: User | null = null;

export function setCurrentUser(user: User | null) {
  currentUser = user;
}

export function getCurrentUser() {
  return currentUser;
}
