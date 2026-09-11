import { User, UserRole } from '../types';
import { MOCK_USERS } from '../mock/users';

class AuthService {
  private currentUser: User = MOCK_USERS[0]; // default to Ahmed Khan (Sales)

  async getCurrentUser(): Promise<User> {
    return { ...this.currentUser };
  }

  async getAllUsers(): Promise<User[]> {
    return [...MOCK_USERS];
  }

  async loginAs(userId: string): Promise<User> {
    const found = MOCK_USERS.find(u => u.id === userId);
    if (found) {
      this.currentUser = { ...found };
      return { ...this.currentUser };
    }
    return { ...this.currentUser };
  }

  async loginWithRole(role: UserRole): Promise<User> {
    const found = MOCK_USERS.find(u => u.role === role) || MOCK_USERS[0];
    this.currentUser = { ...found };
    return { ...this.currentUser };
  }

  async login(email: string): Promise<User> {
    const found = MOCK_USERS.find(u => u.email.toLowerCase() === email.toLowerCase());
    if (found) {
      this.currentUser = { ...found };
      return { ...this.currentUser };
    }
    // fallback to first user
    return { ...this.currentUser };
  }
}

export const authService = new AuthService();
