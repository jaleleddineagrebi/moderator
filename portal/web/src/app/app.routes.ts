import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { AuthService } from './services/auth.service';
import { FeedComponent } from './components/feed/feed.component';
import { PostDetailComponent } from './components/post-detail/post-detail.component';
import { ContactComponent } from './components/contact/contact.component';
import { AdminComponent } from './components/admin/admin.component';

// The gym page is not reachable without a signed-in account; the server then checks the admin list.
const signedInOnly = () => {
  const auth = inject(AuthService);
  return auth.isAuthenticated() ? true : inject(Router).parseUrl('/');
};

export const routes: Routes = [
  {
    path: '',
    component: FeedComponent,
    title: 'Mind Decoded | Daily Psychology & Artificial Intelligence'
  },
  {
    path: 'shorts',
    component: FeedComponent,
    title: 'YouTube Shorts | Mind Decoded'
  },
  {
    path: 'posts/:slug',
    component: PostDetailComponent,
    title: 'Article Reflection | Psychology & AI Portal'
  },
  {
    path: 'contact',
    component: ContactComponent,
    title: 'Contact Us | Mind Decoded'
  },
  {
    path: 'admin',
    component: AdminComponent,
    title: 'Admin Command Center | Mind Decoded'
  },
  {
    path: 'gym',
    canMatch: [signedInOnly],
    loadComponent: () => import('./components/gym/gym.component').then((m) => m.GymComponent),
    title: 'Gym Back Office | Mind Decoded'
  },
  {
    path: '**',
    redirectTo: ''
  }
];

