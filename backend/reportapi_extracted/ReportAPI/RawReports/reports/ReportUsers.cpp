//+------------------------------------------------------------------+
//|                                               Raw Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportUsers.h"
//+------------------------------------------------------------------+
//| Accounts Report                                                  |
//+------------------------------------------------------------------+
BOOL CReportUsers::GenerateHTML(const ReportParams* params)
  {
   int  i,result=TRUE;
   char tmp[256]="";
//--- checks
   if(params==NULL)                                 return(FALSE);
   if(params->users==NULL || params->users_total<1) return(FALSE);
   if(params->filepath[0]==0)                       return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)  return(FALSE);
//--- generation
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".dt    { mso-number-format:\"yyyy\\.mm\\.dd hh\\:mm\"; }\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0>\n");
   fprintf(m_file,"<tr><td colspan=20><font size=2><b>%s</b></font></td></tr>\n",m_info.name);
   fprintf(m_file,"<tr align=right bgcolor=#c0c0c0>");
   fprintf(m_file,"<td align=left>Login</td><td align=left>Name</td><td>Group</td><td>Country</td>"
                  "<td>City</td><td>State</td><td>Zip</td><td>Address</td><td>Phone</td><td>Email</td>"
                  "<td>Comment</td><td>ID</td><td>Status</td><td>Reg.date</td><td>Leverage</td>"
                  "<td>Agent</td><td>Balance</td><td>Credit</td><td>IR</td><td>Taxes</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   UserRecord *user=params->users;
   for(i=0;i<params->users_total;i++,user++)
     {
      //--- background color
      if((i&1)==0) fprintf(m_file,"<tr align=right>");
      else         fprintf(m_file,"<tr align=right bgcolor=#e0e0e0>");
      //--- row
      fprintf(m_file,"<td align=left>%d</td>",user->login);
      fprintf(m_file,"<td align=left nowrap>%s</td>",user->name);
      fprintf(m_file,"<td nowrap>%s</td>",user->group);
      fprintf(m_file,"<td nowrap>%s</td>",user->country);
      fprintf(m_file,"<td nowrap>%s</td>",user->city);
      fprintf(m_file,"<td nowrap>%s</td>",user->state);
      fprintf(m_file,"<td nowrap>%s</td>",user->zipcode);
      fprintf(m_file,"<td nowrap>%s</td>",user->address);
      fprintf(m_file,"<td nowrap>%s</td>",user->phone);
      fprintf(m_file,"<td nowrap>%s</td>",user->email);
      fprintf(m_file,"<td nowrap>%s</td>",user->comment);
      fprintf(m_file,"<td nowrap>%s</td>",user->id);
      fprintf(m_file,"<td nowrap>%s</td>",user->status);
      fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(user->regdate,tmp,sizeof(tmp)-1));
      if(user->leverage>0)
         fprintf(m_file,"<td nowrap style=mso-number-format:\"\\@\";>1 : %d</td>",user->leverage);
      else
         fprintf(m_file,"<td>&nbsp;</td>");
      if(user->agent_account>0)
         fprintf(m_file,"<td>%d</td>",user->agent_account);
      else
         fprintf(m_file,"<td>&nbsp;</td>");
      fprintf(m_file,"<td class=money nowrap>%s</td>",ToMoney(user->balance     ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td class=money nowrap>%s</td>",ToMoney(user->credit      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td class=money nowrap>%s</td>",ToMoney(user->interestrate,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td class=money nowrap>%s</td>",ToMoney(user->taxes       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"</tr>\n");
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->users_total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
   fprintf(m_file,"</table>\n</div></body></html>\n");
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportUsers::GenerateCSV(const ReportParams* params)
  {
   int  i,result=TRUE;
   char tmp[256]="";
//--- checks
   if(params==NULL)                                 return(FALSE);
   if(params->users==NULL || params->users_total<1) return(FALSE);
   if(params->filepath[0]==0)                       return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)  return(FALSE);
//--- report header
   fprintf(m_file,"%s\n",m_info.name);
   fprintf(m_file,"Login;Name;Group;Country;City;State;Zip;Address;Phone;Email;Comment;ID;"
                  "Status;Reg.date;Leverage;Agent;Balance;Credit;IR;Taxes\n");
//--- report rows
   UserRecord *user=params->users;
   for(i=0;i<params->users_total;i++,user++)
     {
      fprintf(m_file,"%d;%s;%s;",user->login,  user->name,   user->group);
      fprintf(m_file,"%s;%s;%s;",user->country,user->city,   user->state);
      fprintf(m_file,"%s;%s;%s;",user->zipcode,user->address,user->phone);
      fprintf(m_file,"%s;%s;%s;",user->email,  user->comment,user->id);
      FormatDateTime(user->regdate,tmp,sizeof(tmp)-1);
      fprintf(m_file,"%s;%s;",user->status,tmp);
      if(user->leverage>0) fprintf(m_file,"1 : %d;",user->leverage);
      else                 fprintf(m_file,";");
      fprintf(m_file,"%d;%.2lf;%.2lf;",user->agent_account,user->balance,user->credit);
      fprintf(m_file,"%.2lf;%.2lf\n",  user->interestrate, user->taxes);
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->users_total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
