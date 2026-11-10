import { Routes } from '@angular/router';
import { FeedComponent } from './components/feed/feed.component';
import { PostDetailComponent } from './components/post-detail/post-detail.component';
import { ContactComponent } from './components/contact/contact.component';

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
    path: '**',
    redirectTo: ''
  }
];

